/**
 * Nexa Analytics Worker
 * 静的サイトのページビュー・滞在時間を収集し、KVに保存する
 */

const SITE_ORIGIN = "https://nexa.nexaworks-jp.workers.dev";
const CORS = {
  "Access-Control-Allow-Origin": SITE_ORIGIN,
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: CORS });
    }

    const url = new URL(request.url);

    // POST /track - ページビューを記録
    if (request.method === "POST" && url.pathname === "/track") {
      try {
        const { path = "/", duration_ms = 0, referrer = "" } =
          await request.json();
        const today = new Date().toISOString().slice(0, 10);

        // パス別総ビュー数（永続）
        const totalKey = `v:${path}`;
        const views =
          parseInt((await env.ANALYTICS.get(totalKey)) || "0") + 1;
        await env.ANALYTICS.put(totalKey, String(views));

        // 日別グローバルカウンター（90日TTL）
        const dayKey = `d:${today}`;
        const dayViews =
          parseInt((await env.ANALYTICS.get(dayKey)) || "0") + 1;
        await env.ANALYTICS.put(dayKey, String(dayViews), {
          expirationTtl: 7776000,
        });

        // 滞在時間の累積（2秒〜60分の範囲のみ記録、90日TTL）
        const dur = parseInt(duration_ms);
        if (dur > 2000 && dur < 3600000) {
          const durKey = `t:${path}`;
          const prev = (await env.ANALYTICS.get(durKey)) || "0,0";
          const [acc, cnt] = prev.split(",");
          await env.ANALYTICS.put(
            durKey,
            `${parseInt(acc) + dur},${parseInt(cnt) + 1}`,
            { expirationTtl: 7776000 }
          );
        }

        // リファラー別カウント（90日TTL）
        if (referrer) {
          const refHost = (() => {
            try {
              return new URL(referrer).hostname;
            } catch {
              return "direct";
            }
          })();
          const refKey = `r:${refHost}`;
          const refVal =
            parseInt((await env.ANALYTICS.get(refKey)) || "0") + 1;
          await env.ANALYTICS.put(refKey, String(refVal), {
            expirationTtl: 7776000,
          });
        }

        return new Response("ok", { headers: CORS });
      } catch {
        return new Response("error", { status: 400, headers: CORS });
      }
    }

    // GET /stats - 集計データを返す（Pythonフェッチャー用）
    if (request.method === "GET" && url.pathname === "/stats") {
      // ページ別ビュー数
      const pageList = await env.ANALYTICS.list({ prefix: "v:" });
      const pages = [];
      for (const k of pageList.keys) {
        const path = k.name.slice(2);
        const views = parseInt((await env.ANALYTICS.get(k.name)) || "0");
        const durRaw = (
          (await env.ANALYTICS.get(`t:${path}`)) || "0,0"
        ).split(",");
        const avgSec =
          parseInt(durRaw[1]) > 0
            ? Math.round(parseInt(durRaw[0]) / parseInt(durRaw[1]) / 1000)
            : 0;
        pages.push({ path, views, avg_seconds: avgSec });
      }
      pages.sort((a, b) => b.views - a.views);

      // 直近30日の日別PV
      const daily = {};
      for (let i = 0; i < 30; i++) {
        const d = new Date();
        d.setDate(d.getDate() - i);
        const day = d.toISOString().slice(0, 10);
        daily[day] = parseInt((await env.ANALYTICS.get(`d:${day}`)) || "0");
      }

      // リファラー一覧
      const refList = await env.ANALYTICS.list({ prefix: "r:" });
      const referrers = [];
      for (const k of refList.keys) {
        const host = k.name.slice(2);
        const cnt = parseInt((await env.ANALYTICS.get(k.name)) || "0");
        referrers.push({ host, count: cnt });
      }
      referrers.sort((a, b) => b.count - a.count);

      return new Response(
        JSON.stringify({
          pages: pages.slice(0, 100),
          daily,
          referrers: referrers.slice(0, 20),
          generated_at: new Date().toISOString(),
        }),
        { headers: { ...CORS, "Content-Type": "application/json" } }
      );
    }

    return new Response("not found", { status: 404 });
  },
};
