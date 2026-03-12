/**
 * Nexa LINE Webhook Worker
 * Cloudflare Workers で動作 - 無料・24時間稼働
 * Claude API 不使用 (固定コマンドのみ)
 *
 * 必要な Cloudflare Worker Secrets:
 *   LINE_CHANNEL_SECRET
 *   LINE_CHANNEL_ACCESS_TOKEN
 *   GITHUB_TOKEN
 *   GITHUB_REPO  (例: "nexaworks-jp/Nexa")
 */

const GITHUB_API = "https://api.github.com";
const LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply";

// ────────────────────────────────────────────────
// 署名検証 (WebCrypto API)
// ────────────────────────────────────────────────
async function verifyLineSignature(bodyText, signature, channelSecret) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(channelSecret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const mac = await crypto.subtle.sign("HMAC", key, enc.encode(bodyText));
  const expected = btoa(String.fromCharCode(...new Uint8Array(mac)));
  return expected === signature;
}

// ────────────────────────────────────────────────
// GitHub API ヘルパー
// ────────────────────────────────────────────────
async function fetchMemory(filename, env) {
  const url = `${GITHUB_API}/repos/${env.GITHUB_REPO}/contents/memory/${filename}`;
  try {
    const resp = await fetch(url, {
      headers: { Authorization: `token ${env.GITHUB_TOKEN}` },
    });
    if (!resp.ok) return {};
    const data = await resp.json();
    const decoded = atob(data.content.replace(/\n/g, ""));
    // UTF-8 デコード (日本語対応)
    const bytes = new Uint8Array(decoded.length);
    for (let i = 0; i < decoded.length; i++) bytes[i] = decoded.charCodeAt(i);
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return {};
  }
}

async function fetchGitHubFile(path, env) {
  const url = `${GITHUB_API}/repos/${env.GITHUB_REPO}/contents/${path}`;
  try {
    const resp = await fetch(url, {
      headers: { Authorization: `token ${env.GITHUB_TOKEN}` },
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    const decoded = atob(data.content.replace(/\n/g, ""));
    const bytes = new Uint8Array(decoded.length);
    for (let i = 0; i < decoded.length; i++) bytes[i] = decoded.charCodeAt(i);
    return new TextDecoder().decode(bytes);
  } catch {
    return null;
  }
}

async function saveMemory(filename, payload, env) {
  const url = `${GITHUB_API}/repos/${env.GITHUB_REPO}/contents/memory/${filename}`;
  const headers = {
    Authorization: `token ${env.GITHUB_TOKEN}`,
    "Content-Type": "application/json",
  };

  // 現在の SHA を取得
  const getResp = await fetch(url, { headers });
  const sha = getResp.ok ? (await getResp.json()).sha : null;

  // UTF-8 → base64
  const jsonBytes = new TextEncoder().encode(
    JSON.stringify(payload, null, 2)
  );
  let binary = "";
  for (const b of jsonBytes) binary += String.fromCharCode(b);
  const content = btoa(binary);

  const body = {
    message: `🤖 webhook: update ${filename}`,
    content,
    ...(sha ? { sha } : {}),
  };

  const putResp = await fetch(url, {
    method: "PUT",
    headers,
    body: JSON.stringify(body),
  });
  return putResp.ok;
}

async function triggerWorkflow(workflow, env) {
  const url = `${GITHUB_API}/repos/${env.GITHUB_REPO}/actions/workflows/${workflow}/dispatches`;
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `token ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github.v3+json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: "main" }),
  });
  return resp.status === 204;
}

// ────────────────────────────────────────────────
// LINE 返信
// ────────────────────────────────────────────────
async function replyLine(replyToken, text, env) {
  await fetch(LINE_REPLY_API, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.LINE_CHANNEL_ACCESS_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      replyToken,
      messages: [{ type: "text", text }],
    }),
  });
}

// ────────────────────────────────────────────────
// コマンドハンドラー (全て無料・API不使用)
// ────────────────────────────────────────────────
async function handleCommand(cmd, env) {
  const c = cmd.trim().toLowerCase();

  // ── レポート ──
  if (["レポート", "report", "r"].includes(c)) {
    const [earnings, risk] = await Promise.all([
      fetchMemory("earnings.json", env),
      fetchMemory("risk_state.json", env),
    ]);
    const total = earnings.total_earnings_jpy || 0;
    const byCh = earnings.by_channel || {};
    const apiCostJpy = ((risk.api_cost_month_usd || 0) * 150).toFixed(0);
    const paused = risk.paused_modules || {};
    const status =
      Object.keys(paused).length === 0
        ? "✅ 正常稼働"
        : `⚠️ ${Object.keys(paused).join(", ")} 停止中`;
    return (
      `📊 現在のレポート\n\n` +
      `💰 累計収益: ¥${total.toLocaleString()}\n` +
      `  note: ¥${(byCh.note || 0).toLocaleString()}\n` +
      `  CW: ¥${(byCh.crowdworks || 0).toLocaleString()}\n\n` +
      `⚙️ 今月のAPI費用: ¥${apiCostJpy}\n` +
      `🔄 総実行回数: ${risk.total_runs || 0}回\n` +
      `状態: ${status}`
    );
  }

  // ── リスク ──
  if (["リスク", "risk"].includes(c)) {
    const risk = await fetchMemory("risk_state.json", env);
    const paused = risk.paused_modules || {};
    const errors = Object.fromEntries(
      Object.entries(risk.consecutive_errors || {}).filter(([, v]) => v > 0)
    );
    const costToday = ((risk.api_cost_today_usd || 0) * 150).toFixed(0);
    const costMonth = ((risk.api_cost_month_usd || 0) * 150).toFixed(0);
    let msg =
      `🛡️ リスク状態\n\n` +
      `本日のAPI費用: ¥${costToday} / ¥45上限\n` +
      `今月のAPI費用: ¥${costMonth} / ¥750上限`;
    if (Object.keys(paused).length > 0)
      msg += `\n\n⏸️ 停止中: ${Object.keys(paused).join(", ")}`;
    if (Object.keys(errors).length > 0)
      msg += `\n⚠️ エラー中: ${JSON.stringify(errors)}`;
    if (Object.keys(paused).length === 0 && Object.keys(errors).length === 0)
      msg += "\n\n✅ 全モジュール正常";
    return msg;
  }

  // ── 今すぐ実行 ──
  if (["実行", "run", "今すぐ", "now"].includes(c)) {
    const ok = await triggerWorkflow("run.yml", env);
    return ok
      ? "▶️ 今すぐ実行を開始しました\n\n完了後にLINEで通知されます。"
      : "⚠️ 実行トリガーに失敗しました\nGitHubトークンを確認してください。";
  }

  // ── 週次改善 ──
  if (["週次", "週次改善", "weekly", "改善してrun", "週次run"].includes(c)) {
    const ok = await triggerWorkflow("weekly.yml", env);
    return ok
      ? "🔧 週次改善を開始しました\n\n完了まで約30分かかります。"
      : "⚠️ 実行トリガーに失敗しました\nGitHubトークンを確認してください。";
  }

  // ── 停止 ──
  if (["停止", "stop", "pause"].includes(c)) {
    const risk = await fetchMemory("risk_state.json", env);
    const now = new Date().toISOString();
    if (!risk.paused_modules) risk.paused_modules = {};
    for (const mod of ["note", "x", "crowdworks", "saas"]) {
      risk.paused_modules[mod] = now;
    }
    const ok = await saveMemory("risk_state.json", risk, env);
    return ok
      ? "⏸️ 全モジュールを停止しました。\n次の定時実行から反映されます。\n再開: 「再開」と送ってください。"
      : "⚠️ 停止に失敗しました。\nGitHubトークンを確認してください。";
  }

  // ── 再開 ──
  if (["再開", "resume", "start"].includes(c)) {
    const risk = await fetchMemory("risk_state.json", env);
    risk.paused_modules = {};
    risk.consecutive_errors = {};
    const ok = await saveMemory("risk_state.json", risk, env);
    return ok
      ? "▶️ 全モジュールを再開しました。\n次の定時実行から動き始めます。"
      : "⚠️ 再開に失敗しました。\nGitHubトークンを確認してください。";
  }

  // ── 提案 ──
  if (["提案", "proposals"].includes(c)) {
    const proposals = await fetchMemory("proposals.json", env);
    const items = proposals.applied || [];
    if (!items.length)
      return "📋 まだ提案文はありません。\n次の定時実行で生成されます。";
    const latest = items[items.length - 1];
    let msg = `📋 最新の提案文（全${items.length}件）\n\n`;
    msg += `【案件】${latest.job_title || "不明"}\n`;
    if (latest.estimated_price)
      msg += `【金額】${latest.estimated_price}　【納期】${latest.estimated_days || "未定"}\n`;
    if (latest.job_url) msg += `【URL】${latest.job_url}\n`;
    msg += `\n${(latest.proposal_text || "").slice(0, 1000)}`;
    return msg;
  }

  // ── 改善 (improvements.md を読むだけ・API不使用) ──
  if (["改善", "improve", "i"].includes(c)) {
    const content = await fetchGitHubFile(
      "proposals/improvements.md",
      env
    );
    if (content) {
      const sections = content.split("\n## ");
      if (sections.length >= 2) {
        return `📈 最新の改善分析\n\n## ${sections[1].slice(0, 600)}`;
      }
    }
    return "📈 改善分析はまだありません。\n次の定時実行後に生成されます。";
  }

  // ── ヘルプ ──
  if (["ヘルプ", "help", "h", "?"].includes(c)) {
    return (
      "🤖 AIカンパニー コマンド一覧\n\n" +
      "📊 レポート — 収益・状態を表示\n" +
      "🛡️ リスク — リスク状態を表示\n" +
      "▶️ 実行 — 今すぐ実行\n" +
      "🔧 週次改善 — 改善を今すぐ実行\n" +
      "📋 提案 — 最新の提案文を確認\n" +
      "📈 改善 — 最新の改善分析を表示\n" +
      "⏸️ 停止 — 全モジュールを停止\n" +
      "▶️ 再開 — 全モジュールを再開\n" +
      "❓ ヘルプ — このメッセージ"
    );
  }

  // ── 未認識コマンド (AI不使用 = 無料) ──
  return "❓ コマンドが認識できませんでした。\n\n「ヘルプ」でコマンド一覧を確認してください。";
}

// ────────────────────────────────────────────────
// Worker エントリーポイント
// ────────────────────────────────────────────────
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // ヘルスチェック (UptimeRobot 等)
    if (request.method === "GET" && ["/", "/health"].includes(url.pathname)) {
      return new Response("OK - Nexa LINE Webhook", { status: 200 });
    }

    // LINE Webhook エンドポイント
    if (request.method === "POST" && url.pathname === "/webhook") {
      const bodyText = await request.text();
      const signature = request.headers.get("X-Line-Signature") || "";

      // 署名検証
      if (env.LINE_CHANNEL_SECRET) {
        const valid = await verifyLineSignature(
          bodyText,
          signature,
          env.LINE_CHANNEL_SECRET
        );
        if (!valid) {
          return new Response("Forbidden", { status: 403 });
        }
      }

      // 200 を先に返し、ctx.waitUntil で処理を継続
      const processEvents = async () => {
        try {
          const data = JSON.parse(bodyText);
          for (const event of data.events || []) {
            if (event.type !== "message") continue;
            if (event.message?.type !== "text") continue;
            const text = event.message.text || "";
            const replyToken = event.replyToken || "";
            const reply = await handleCommand(text, env);
            await replyLine(replyToken, reply, env);
          }
        } catch (e) {
          console.error("[Webhook] Error:", e);
        }
      };

      ctx.waitUntil(processEvents());

      return new Response("OK", { status: 200 });
    }

    return new Response("Not Found", { status: 404 });
  },
};
