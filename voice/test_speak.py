"""
voice/test_speak.py — 配信機能テスト用スクリプト

使い方:
  cd Nexa
  python -m voice.test_speak
  python -m voice.test_speak "テキストを指定する場合"
"""

import sys
from voice import speak, synthesize

DEFAULT_TEXT = "こんにちは。私はソフィア、AIとして生まれたばかりの存在です。"


def main() -> None:
    text = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TEXT
    print(f"[TTS] {text}")
    try:
        speak(text)
        print("[TTS] 再生完了")
    except Exception as e:
        print(f"[TTS] エラー: {e}")
        print("VOICEVOXが起動しているか確認してください。")


if __name__ == "__main__":
    main()
