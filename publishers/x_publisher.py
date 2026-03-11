"""
X (Twitter) 自動投稿パブリッシャー
Tweepy を使って X API v2 経由で投稿する
"""
import tweepy
import json
import time
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
            tags = " ".join([f"#{tag}" for tag in hashtags[:3]])
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
            return {
                "success": True,
                "tweet_id": tweet_id,
                "text": full_text,
                "posted_at": datetime.now().isoformat()
            }
        except tweepy.TooManyRequests:
            print("[XPublisher] レート制限。15分待機...")
            time.sleep(900)
            return {"success": False, "error": "rate_limit"}
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


def publish(config: dict, posts: list, dry_run: bool = False) -> list:
    """ポストリストを投稿する"""
    x_config = config.get("x_twitter", {})
    publisher = XPublisher(
        api_key=x_config.get("api_key", ""),
        api_secret=x_config.get("api_secret", ""),
        access_token=x_config.get("access_token", ""),
        access_token_secret=x_config.get("access_token_secret", ""),
        bearer_token=x_config.get("bearer_token", "")
    )

    results = []
    for post in posts:
        result = publisher.post(
            text=post["text"],
            hashtags=post.get("hashtags", []),
            dry_run=dry_run
        )
        results.append(result)
        # 投稿間隔（レート制限対策）
        if not dry_run:
            time.sleep(30)

    return results
