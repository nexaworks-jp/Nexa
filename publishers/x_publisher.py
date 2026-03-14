"""
X (Twitter) 自動投稿パブリッシャー
Tweepy を使って X API v2 経由で投稿する
"""
import tweepy
import json
import time
import random
from datetime import datetime


class XPublisher:
    def __init__(self, api_key: str, api_secret: str, access_token: str,
                 access_token_secret: str, bearer_token: str):
        self.configured = all([api_key, api_secret, access_token,
                               access_token_secret, bearer_token,
                               api_key != "YOUR_X_API_KEY"])
        if self.configured:
            self.client = tweepy.Client(
                bearer_token=bearer_token,
                consumer_key=api_key,
                consumer_secret=api_secret,
                access_token=access_token,
                access_token_secret=access_token_secret
            )
        else:
            self.client = None

    def post(self, text: str, hashtags: list, dry_run: bool = False) -> dict:
        """ツイートを投稿する"""
        full_text = text
        if hashtags:
            # ハッシュタグは2個まで（3個以上はエンゲージメント低下・シャドーバンリスク）
            tags = " ".join([f"#{tag}" for tag in hashtags[:2]])
            if len(full_text) + len(tags) + 1 <= 280:
                full_text = f"{full_text}\n{tags}"

        if dry_run:
            print(f"[XPublisher] DRY RUN: {full_text[:80]}...")
            return {"success": True, "dry_run": True}

        if not self.configured:
            # 未設定の場合はログに保存
            return self._save_to_log(full_text)

        try:
            response = self.client.create_tweet(text=full_text)
            tweet_id = response.data["id"]
            print(f"[XPublisher] 投稿成功: tweet_id={tweet_id}")
            result = {
                "success": True,
                "tweet_id": tweet_id,
                "text": full_text,
                "posted_at": datetime.now().isoformat()
            }
            _save_tweet_id(tweet_id)
            return result
        except tweepy.TooManyRequests:
            print("[XPublisher] レート制限。15分待機...")
            time.sleep(900)
            return {"success": False, "error": "rate_limit"}
        except tweepy.Forbidden as e:
            print(f"[XPublisher] 403 Forbidden: アプリの書き込み権限が不足しています。"
                  f"developer.twitter.com でアプリのPermissionsを'Read and Write'に変更し、"
                  f"アクセストークンを再発行してconfig.jsonを更新してください。")
            return {"success": False, "error": "403_forbidden_check_permissions"}
        except Exception as e:
            print(f"[XPublisher] 投稿エラー: {e}")
            return {"success": False, "error": str(e)}

    def _save_to_log(self, text: str) -> dict:
        """未設定時はログファイルに保存"""
        import os
        log_dir = "drafts"
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{log_dir}/x_post_{timestamp}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[XPublisher] ログ保存: {filename}")
        return {"success": True, "saved_to": filename}


def _save_tweet_id(tweet_id: str):
    """投稿したtweetIDをmemory/tweet_history.jsonに保存（エンゲージメント追跡用）"""
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory", "tweet_history.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    history = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass
    history.append({"tweet_id": tweet_id, "posted_at": datetime.now().isoformat()})
    # 直近200件のみ保持
    history = history[-200:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _last_posted_minutes_ago() -> float:
    """最後の投稿から何分経ったか（tweet_history.jsonを参照）"""
    import os
    from datetime import datetime, timezone
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory", "tweet_history.json")
    if not os.path.exists(path):
        return 9999
    try:
        with open(path, "r", encoding="utf-8") as f:
            history = json.load(f)
        if not history:
            return 9999
        last = history[-1].get("posted_at", "")
        last_dt = datetime.fromisoformat(last)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - last_dt).total_seconds() / 60
    except Exception:
        return 9999


def publish(config: dict, posts: list, dry_run: bool = False) -> list:
    """ポストリストを投稿する（1セッション最大2件・直近90分以内はスキップ）"""
    if not posts:
        return []

    x_config = config.get("x_twitter", {})
    publisher = XPublisher(
        api_key=x_config.get("api_key", ""),
        api_secret=x_config.get("api_secret", ""),
        access_token=x_config.get("access_token", ""),
        access_token_secret=x_config.get("access_token_secret", ""),
        bearer_token=x_config.get("bearer_token", "")
    )

    # 直近90分以内に投稿済みならスキップ（連投Bot判定回避）
    if not dry_run:
        minutes_ago = _last_posted_minutes_ago()
        if minutes_ago < 90:
            print(f"[XPublisher] 前回投稿から{minutes_ago:.0f}分。90分未満のためスキップ。")
            return []

    # 1セッション最大2件、ランダムで1か2に変動（毎回同数はBot判定されやすい）
    max_per_session = random.choices([1, 2], weights=[60, 40])[0]
    selected = posts[:max_per_session]
    print(f"[XPublisher] 今回投稿: {len(selected)}件 / 生成済み{len(posts)}件")

    results = []
    for post in selected:
        result = publisher.post(
            text=post["text"],
            hashtags=post.get("hashtags", []),
            dry_run=dry_run
        )
        results.append(result)
        # 投稿間隔：3〜8分のランダム（数秒間隔はBot判定リスク大）
        if not dry_run and post != selected[-1]:
            interval = random.randint(180, 480)
            print(f"[XPublisher] 次の投稿まで{interval//60}分{interval%60}秒待機...")
            time.sleep(interval)

    return results
