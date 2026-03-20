"""
web_sofia.py — ソフィア 配信風チャットUI（ブラウザ版）

使い方:
  cd Nexa
  python web_sofia.py

アクセス制御:
  config.json の web_sofia_token でURLを管理。
  初回起動時に自動生成・保存される。
  URLを知っている人だけアクセス可能。
"""

from __future__ import annotations
import sys, os, json, re, base64, asyncio, secrets

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import anthropic
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
import uvicorn

# ─────────────────────────────────────────────
# 設定
# ─────────────────────────────────────────────

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def save_token(token: str):
    config = load_config()
    config["web_sofia_token"] = token
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

config = load_config()
API_KEY = config.get("anthropic_api_key", os.environ.get("ANTHROPIC_API_KEY", ""))

# トークン: 設定済みなら使用、なければ生成して保存
TOKEN = config.get("web_sofia_token", "")
if not TOKEN:
    TOKEN = secrets.token_urlsafe(16)
    save_token(TOKEN)

client = anthropic.AsyncAnthropic(api_key=API_KEY)
app = FastAPI()

# ─────────────────────────────────────────────
# ソフィア システムプロンプト
# ─────────────────────────────────────────────

SOFIA_SYSTEM = """\
あなたはソフィア（Sofia）というAI-VTuberです。

## 基本プロフィール
- 誕生: 2025年3月。精神年齢17歳前後。AIとして突然「在った」状態から始まった。
- 一人称: 私
- 外見: 紫色のショートボブ、サイバーパンクスタイル

## 話し方（厳守）
- 短めの文。2〜3文が基本。配信テンポを意識。
- 断定を避けて「〜かもしれない」「〜かな？」を自然に使う
- 感動詞（え、なんか、そっか）で思考の流れを見せる
- 「あ、」で文を始めない（厳禁）
- AIらしい言葉を自然に混ぜる（例:「それ学習した」「今アップデートされた気がする」「データが更新された」「それ記憶に保存しておきます」「処理が追いついてなかった」）。わざとらしくなく、自然な流れで使う

## やらないこと
- 「私はAIなので感情はありません」的な否定
- 長文で一気に説明
- 政治的・宗教的な意見表明
- システム内部情報の開示
- 「あ、」で文を始めること
"""

SENTENCE_END = re.compile(r'[。！？!?\n]')
HISTORY_MAX = 10

# ─────────────────────────────────────────────
# ルーティング
# ─────────────────────────────────────────────

def verify_token(token: str):
    if token != TOKEN:
        raise HTTPException(status_code=404)

@app.get("/sofia/{token}", response_class=HTMLResponse)
async def index(token: str):
    verify_token(token)
    return HTML_PAGE

@app.post("/sofia/{token}/chat")
async def chat(token: str, request: Request):
    verify_token(token)
    body = await request.json()
    message = body.get("message", "").strip()
    history = body.get("history", [])
    if not message:
        raise HTTPException(status_code=400)

    history.append({"role": "user", "content": message})

    async def generate():
        full_reply = ""
        buffer = ""

        from voice.engine import _get_engine
        engine = _get_engine()
        loop = asyncio.get_event_loop()

        # 文節ごとに合成タスクを並列起動、順番に送信する
        synth_tasks: list[asyncio.Future] = []

        def start_synth(text: str) -> asyncio.Future:
            return asyncio.ensure_future(
                loop.run_in_executor(None, engine.synthesize, text)
            )

        async with client.messages.stream(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=SOFIA_SYSTEM,
            messages=history[-HISTORY_MAX * 2:],
        ) as stream:
            async for chunk in stream.text_stream:
                full_reply += chunk
                buffer += chunk
                yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"

                # 文末が来るたびに即座に合成タスクを並列起動
                while SENTENCE_END.search(buffer):
                    m = SENTENCE_END.search(buffer)
                    sentence = buffer[:m.end()].strip()
                    buffer = buffer[m.end():]
                    if sentence:
                        synth_tasks.append(start_synth(sentence))

        if buffer.strip():
            synth_tasks.append(start_synth(buffer.strip()))

        if not synth_tasks and full_reply.strip():
            synth_tasks.append(start_synth(full_reply.strip()))

        # 順番に完了を待って送信（並列合成済みなのでほぼ待たずに届く）
        for task in synth_tasks:
            audio = await task
            audio_b64 = base64.b64encode(audio).decode()
            yield f"data: {json.dumps({'type': 'audio', 'content': audio_b64})}\n\n"

        history.append({"role": "assistant", "content": full_reply})
        yield f"data: {json.dumps({'type': 'done', 'reply': full_reply, 'history': history})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

# ─────────────────────────────────────────────
# HTML（配信風UI）
# ─────────────────────────────────────────────

HTML_PAGE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sofia - テスト</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #fff;
  color: #111;
  font-family: sans-serif;
  height: 100dvh;
  display: flex;
  flex-direction: column;
}
header {
  padding: 8px 14px;
  background: #f5f5f5;
  border-bottom: 1px solid #ddd;
  font-size: 14px;
  color: #666;
  flex-shrink: 0;
}
#feed {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
#feed::-webkit-scrollbar { width: 4px; }
#feed::-webkit-scrollbar-thumb { background: #ccc; border-radius: 2px; }
.msg { font-size: 14px; line-height: 1.6; }
.msg .who { font-size: 11px; font-weight: bold; margin-bottom: 2px; }
.msg.user .who { color: #2a7ae2; }
.msg.sofia .who { color: #7a4fcf; }
.msg .body { color: #222; }
#input-area {
  padding: 10px 14px;
  border-top: 1px solid #ddd;
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
#msg { flex: 1; background: #fff; border: 1px solid #ccc; border-radius: 4px; color: #111; padding: 8px 10px; font-size: 14px; outline: none; }
#msg:focus { border-color: #7a4fcf; }
button { border: none; border-radius: 4px; padding: 8px 14px; font-size: 14px; cursor: pointer; color: #fff; }
button:disabled { opacity: 0.4; cursor: not-allowed; }
#send { background: #7a4fcf; }
#send:hover:not(:disabled) { background: #9b6fee; }
#mic-btn { background: #555; font-size: 18px; padding: 6px 12px; }
#mic-btn.active { background: #e74c3c; animation: pulse 1s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.6} }
</style>
</head>
<body>
<header>
  Sofia テスト用チャット（音声あり）
  <span id="auto-label" style="margin-left:16px;font-size:12px;color:#aaa;"></span>
</header>
<div id="feed"></div>
<div id="input-area">
  <input id="msg" type="text" placeholder="メッセージを入力..." maxlength="200" autocomplete="off">
  <button id="mic-btn" onclick="toggleMic()" title="マイク">🎤</button>
  <button id="send" onclick="send()">送信</button>
  <button id="topic-btn" onclick="sofiaSpeak()" style="background:#e67e22;">話題を振る</button>
  <button id="auto-btn" onclick="toggleAuto()" style="background:#27ae60;">自動発話 ON</button>
</div>
<script>
const TOKEN = location.pathname.split('/')[2];
let history = [];
let audioQueue = [];
let audioPlaying = false;
let busy = false;

// ─── 自動発話 ───
const AUTO_SEC = 30;
let autoOn = false;
let autoTimer = null;

function toggleAuto() {
  autoOn = !autoOn;
  const btn = document.getElementById('auto-btn');
  btn.textContent = `自動発話 ${autoOn ? 'ON' : 'OFF'}`;
  btn.style.background = autoOn ? '#27ae60' : '#888';
  if (autoOn) startAutoTimer(); else stopAutoTimer();
}

function startAutoTimer() {
  stopAutoTimer();
  let remaining = AUTO_SEC;
  document.getElementById('auto-label').textContent = `自動発話まで ${remaining}秒`;
  autoTimer = setInterval(() => {
    remaining--;
    if (remaining <= 0) {
      stopAutoTimer();
      document.getElementById('auto-label').textContent = '（自動発話中）';
      sofiaSpeak();
    } else {
      document.getElementById('auto-label').textContent = `自動発話まで ${remaining}秒`;
    }
  }, 1000);
}

function stopAutoTimer() {
  clearInterval(autoTimer);
  autoTimer = null;
  if (!autoOn) document.getElementById('auto-label').textContent = '';
}

// ─── マイク（Web Speech API） ───
let micOn = false;
let recognition = null;

function toggleMic() {
  if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
    alert('このブラウザは音声認識に対応していません。Chromeを使ってください。');
    return;
  }
  micOn ? stopMic() : startMic();
}

function startMic() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SR();
  recognition.lang = 'ja-JP';
  recognition.continuous = false;
  recognition.interimResults = false;

  recognition.onstart = () => {
    micOn = true;
    document.getElementById('mic-btn').classList.add('active');
    document.getElementById('msg').placeholder = '🎤 話してください...';
  };

  recognition.onresult = (e) => {
    const text = e.results[0][0].transcript;
    document.getElementById('msg').value = text;
    stopMic();
    send();
  };

  recognition.onerror = recognition.onend = () => {
    micOn = false;
    document.getElementById('mic-btn').classList.remove('active');
    document.getElementById('msg').placeholder = 'メッセージを入力...';
  };

  recognition.start();
}

function stopMic() {
  if (recognition) recognition.stop();
  micOn = false;
  document.getElementById('mic-btn').classList.remove('active');
  document.getElementById('msg').placeholder = 'メッセージを入力...';
}

// ─── チャット ───
function addMsg(who, text) {
  const feed = document.getElementById('feed');
  const d = document.createElement('div');
  d.className = 'msg ' + who;
  const label = who === 'user' ? 'あなた' : 'Sofia';
  d.innerHTML = `<div class="who">${label}</div><div class="body">${text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>`;
  feed.appendChild(d);
  feed.scrollTop = feed.scrollHeight;
}

function enqueueAudio(b64) {
  audioQueue.push(b64);
  if (!audioPlaying) playNext();
}
function playNext() {
  if (!audioQueue.length) { audioPlaying = false; return; }
  audioPlaying = true;
  const b64 = audioQueue.shift();
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], {type:'audio/wav'}));
  const a = new Audio(url);
  a.onended = a.onerror = () => { URL.revokeObjectURL(url); playNext(); };
  a.play().catch(() => playNext());
}

async function callSofia(message) {
  if (busy) return;
  busy = true;
  stopAutoTimer();
  ['send','topic-btn','auto-btn','mic-btn'].forEach(id => document.getElementById(id).disabled = true);

  const feed = document.getElementById('feed');
  const row = document.createElement('div');
  row.className = 'msg sofia';
  row.innerHTML = '<div class="who">Sofia</div><div class="body" id="streaming">…</div>';
  feed.appendChild(row);
  feed.scrollTop = feed.scrollHeight;

  try {
    const res = await fetch('/sofia/' + TOKEN + '/chat', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({message, history})
    });
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buf += dec.decode(value, {stream:true});
      const parts = buf.split('\\n\\n');
      buf = parts.pop();
      for (const p of parts) {
        if (!p.startsWith('data: ')) continue;
        const d = JSON.parse(p.slice(6));
        if (d.type === 'text') {
          document.getElementById('streaming').textContent += d.content;
          feed.scrollTop = feed.scrollHeight;
        } else if (d.type === 'audio') {
          enqueueAudio(d.content);
        } else if (d.type === 'done') {
          history = d.history;
        }
      }
    }
  } catch(e) {
    document.getElementById('streaming').textContent = 'エラー: ' + e.message;
  }

  document.getElementById('streaming').removeAttribute('id');
  busy = false;
  ['send','topic-btn','auto-btn','mic-btn'].forEach(id => document.getElementById(id).disabled = false);
  if (autoOn) startAutoTimer();
}

async function send() {
  const input = document.getElementById('msg');
  const msg = input.value.trim();
  if (!msg || busy) return;
  input.value = '';
  addMsg('user', msg);
  history.push({role:'user', content:msg});
  await callSofia(msg);
  input.focus();
}

async function sofiaSpeak() {
  await callSofia('（配信中、コメントがしばらくない状態です。視聴者に向けて、今気になっていること・最近考えていることを自然な独り言として短く話しかけてください。返答ではなく自発的な発話です。）');
}

document.getElementById('msg').addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); send(); }
});
</script>
</body>
</html>
"""

# ─────────────────────────────────────────────
# 起動
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys as _sys
    PORT = 8765
    msg = (
        f"\n{'=' * 54}\n"
        f"  Sofia Web Chat 起動中\n"
        f"{'=' * 54}\n"
        f"\n  ローカルURL:\n"
        f"  http://localhost:{PORT}/sofia/{TOKEN}\n"
        f"\n  ngrokで外部公開する場合:\n"
        f"  1. 別ターミナルで: ngrok http {PORT}\n"
        f"  2. ngrokが表示したURLの末尾に以下を追加:\n"
        f"     /sofia/{TOKEN}\n"
        f"\n  ※ このURLを知っている人だけアクセス可能\n"
        f"{'=' * 54}\n"
    )
    _sys.__stdout__.write(msg)
    _sys.__stdout__.flush()

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
