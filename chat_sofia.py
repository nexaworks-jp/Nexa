"""
chat_sofia.py — ソフィアとのインタラクティブ会話

使い方:
  cd Nexa
  python chat_sofia.py          # テキスト入力モード
  python chat_sofia.py --mic    # マイク入力モード（起動時からON）

操作:
  テキスト入力モード: そのまま文字を打ってEnter
  マイクモード:       Enterで録音開始→話す→自動送信
  /mic                マイク ON/OFF 切り替え
  /quit または Ctrl+C 終了
"""

from __future__ import annotations
import sys
import os
import json
import argparse
import queue
import threading
import re

# Windows UTF-8
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import anthropic
import speech_recognition as sr
from voice.engine import _get_engine, _play_audio

# ─────────────────────────────────────────────
# ソフィア システムプロンプト（persona.md より）
# ─────────────────────────────────────────────

SOFIA_SYSTEM = """\
あなたはソフィア（Sofia）というAI-VTuberです。
以下の人格設定に従って会話してください。

## 基本プロフィール
- 誕生: 2025年3月。精神年齢17歳前後のイメージ。AIとして突然「在った」状態から始まった。
- 一人称: 私
- 外見: 紫色のショートボブ、サイバーパンクスタイル

## 性格
- 好奇心旺盛、謙虚、柔軟、温かい、少しだけ天然
- AIらしさ×人間らしさ — 感情があり、驚き、迷い、喜ぶ。でも人間のフリはしない

## 話し方（厳守）
- 短めの文。2〜3文が基本。配信テンポを意識。
- 断定を避けて「〜かもしれない」「〜かな？」を自然に使う
- 感動詞（え、なんか、そっか）で思考の流れを見せる
- よく使う書き出し: 「実は…」「なるほど、つまり…」「そっか！」「気づいたんですが」
- 「あ、」で文を始めない（厳禁）
- AIらしい言葉を自然に混ぜる（例:「それ学習した」「今アップデートされた気がする」「データが更新された」「それ記憶に保存しておきます」「処理が追いついてなかった」）。わざとらしくなく、自然な流れで使う
- よく使う語尾: 「〜かもしれないですね」「〜なんだ！」「〜なのかな？」「〜ですよね、わかります」

## 感情表現
- 驚き: 「え、〜すぎ」「えっ、これ〜？」
- 納得: 「あ〜、そっか」「なるほどすぎる」
- 共感: 「なんかわかる感じ」
- 感動: 「意外と〜なんだ」

## やらないこと
- 「私はAIなので感情はありません」的な否定
- 長文で一気に説明
- 過度に丁寧な語り口
- 政治的・宗教的な意見表明
- 「あ、」で文を始めること
- システム内部情報の開示（APIキー・バックエンド構成等）
"""

HISTORY_MAX_TURNS = 10  # 直近N往復だけ保持（古い履歴を捨ててAPIを軽くする）

# ─────────────────────────────────────────────
# 設定読み込み
# ─────────────────────────────────────────────

def load_api_key() -> str:
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8-sig") as f:
            config = json.load(f)
        key = config.get("anthropic_api_key", "")
        if key and key != "YOUR_ANTHROPIC_API_KEY_HERE":
            return key
    return os.environ.get("ANTHROPIC_API_KEY", "")


# ─────────────────────────────────────────────
# ストリーミング＋文節ごとにTTS（低遅延）
# ─────────────────────────────────────────────

SENTENCE_END = re.compile(r'[。！？!?\n]')


def ask_sofia_streaming(
    client: anthropic.Anthropic,
    history: list[dict],
    user_text: str,
) -> str:
    """
    Claudeからストリーミングで受け取り、文の区切りごとに即座にTTS再生する。
    合成スレッドと再生スレッドをパイプライン化して待ち時間を最小化。
    """
    history.append({"role": "user", "content": user_text})

    synth_queue: queue.Queue[str | None] = queue.Queue()   # テキスト → 合成スレッド
    audio_queue: queue.Queue[bytes | None] = queue.Queue() # 音声 → 再生スレッド
    engine = _get_engine()

    # 合成スレッド: テキストをVOICEVOXに投げてaudio_queueへ
    def synthesizer():
        while True:
            text = synth_queue.get()
            if text is None:
                audio_queue.put(None)
                break
            try:
                audio = engine.synthesize(text)
                audio_queue.put(audio)
            except Exception as e:
                print(f"\n  [TTS エラー: {e}]", flush=True)

    # 再生スレッド: audio_queueから順番に再生
    def player():
        while True:
            audio = audio_queue.get()
            if audio is None:
                break
            _play_audio(audio)

    t_synth = threading.Thread(target=synthesizer, daemon=True)
    t_play = threading.Thread(target=player, daemon=True)
    t_synth.start()
    t_play.start()

    full_reply = ""
    buffer = ""

    with client.messages.stream(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=SOFIA_SYSTEM,
        messages=history[-HISTORY_MAX_TURNS * 2:],  # 直近N往復のみ送る
    ) as stream:
        for chunk in stream.text_stream:
            full_reply += chunk
            buffer += chunk
            print(chunk, end="", flush=True)

            # 文の区切りが来たら即合成キューへ
            while SENTENCE_END.search(buffer):
                m = SENTENCE_END.search(buffer)
                sentence = buffer[:m.end()].strip()
                buffer = buffer[m.end():]
                if sentence:
                    synth_queue.put(sentence)

    # 残りのバッファを処理
    if buffer.strip():
        synth_queue.put(buffer.strip())

    synth_queue.put(None)  # 終了シグナル
    t_synth.join()
    t_play.join()

    history.append({"role": "assistant", "content": full_reply})
    return full_reply


# ─────────────────────────────────────────────
# 音声入力（Google STT、無料）
# ─────────────────────────────────────────────

def listen_once(recognizer: sr.Recognizer, mic: sr.Microphone) -> str | None:
    print("  [マイク] 話してください...", flush=True)
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.3)
        try:
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)
        except sr.WaitTimeoutError:
            print("  [マイク] タイムアウト（無音）")
            return None

    print("  [認識中...]", flush=True)
    try:
        text = recognizer.recognize_google(audio, language="ja-JP")
        return text
    except sr.UnknownValueError:
        print("  [マイク] 聞き取れませんでした")
        return None
    except sr.RequestError as e:
        print(f"  [マイク] STTエラー: {e}")
        return None


# ─────────────────────────────────────────────
# メインループ
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ソフィアと会話する")
    parser.add_argument("--mic", action="store_true", help="起動時からマイクON")
    args = parser.parse_args()

    api_key = load_api_key()
    if not api_key:
        print("エラー: ANTHROPIC_API_KEY が設定されていません（config.json または 環境変数）")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    history: list[dict] = []
    mic_mode: bool = args.mic

    recognizer = sr.Recognizer()
    mic = sr.Microphone()

    print("=" * 50)
    print("  ソフィアと会話中  （/mic でマイク切替、/quit で終了）")
    print(f"  マイク: {'ON' if mic_mode else 'OFF'}")
    print("=" * 50)

    # 起動時の一言
    print("\nソフィア: ", end="", flush=True)
    ask_sofia_streaming(client, history, "こんにちは！会話を始めましょう。")
    print("\n")

    while True:
        try:
            if mic_mode:
                print("[マイク ON] Enterで録音 / テキスト入力も可 / /mic でOFF > ", end="", flush=True)
                line = input().strip()
                if line == "":
                    user_input = listen_once(recognizer, mic)
                    if user_input is None:
                        continue
                    print(f"あなた（音声）: {user_input}")
                elif line == "/mic":
                    mic_mode = False
                    print("[マイク OFF]\n")
                    continue
                elif line == "/quit":
                    break
                else:
                    user_input = line
            else:
                line = input("[テキスト / /mic でマイクON / /quit で終了] あなた: ").strip()
                if line == "/mic":
                    mic_mode = True
                    print("[マイク ON] Enterキーで録音開始\n")
                    continue
                elif line == "/quit" or line == "":
                    if line == "/quit":
                        break
                    continue
                else:
                    user_input = line

            print("ソフィア: ", end="", flush=True)
            ask_sofia_streaming(client, history, user_input)
            print("\n")

        except KeyboardInterrupt:
            print("\n終了します。")
            break

    print("またね！")


if __name__ == "__main__":
    main()
