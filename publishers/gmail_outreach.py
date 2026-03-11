"""
Gmail 自動営業メール送信
Gmail API を使って営業メールを自動送信する
OAuth2認証が必要（初回のみ）
"""
import json
import os
import base64
from email.mime.text import MIMEText
from datetime import datetime


def get_gmail_service():
    """Gmail APIサービスを取得（OAuth2）"""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        SCOPES = ['https://www.googleapis.com/auth/gmail.send']
        creds = None
        token_path = os.path.join(os.path.dirname(__file__), "..", "gmail_token.json")
        creds_path = os.path.join(os.path.dirname(__file__), "..", "gmail_credentials.json")

        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            elif os.path.exists(creds_path):
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
                creds = flow.run_local_server(port=0)
                with open(token_path, "w") as f:
                    f.write(creds.to_json())
            else:
                return None

        return build('gmail', 'v1', credentials=creds)

    except ImportError:
        print("[GmailOutreach] google-auth-oauthlib が未インストール。pip install google-auth-oauthlib google-api-python-client")
        return None
    except Exception as e:
        print(f"[GmailOutreach] Gmail API初期化エラー: {e}")
        return None


def send_email(service, to: str, subject: str, body: str, from_email: str = "me") -> dict:
    """メールを送信する"""
    try:
        message = MIMEText(body, 'plain', 'utf-8')
        message['to'] = to
        message['subject'] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        result = service.users().messages().send(
            userId='me',
            body={'raw': raw}
        ).execute()
        return {"success": True, "message_id": result.get("id")}
    except Exception as e:
        return {"success": False, "error": str(e)}


def save_outreach_draft(to: str, subject: str, body: str, context: str) -> dict:
    """Gmail未設定時はドラフトとして保存"""
    draft_dir = os.path.join(os.path.dirname(__file__), "..", "outreach_drafts")
    os.makedirs(draft_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(draft_dir, f"email_{timestamp}.txt")
    content = f"""To: {to}
Subject: {subject}
Context: {context}

{body}
"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[GmailOutreach] ドラフト保存: {filename}")
    return {"success": True, "saved_to": filename}


def send_outreach(config: dict, saas_result: dict, target_emails: list, dry_run: bool = False) -> list:
    """
    営業メールを送信する
    target_emails: 送信先メールアドレスのリスト
    """
    email_template = saas_result.get("email_template", {})
    idea = saas_result.get("idea", {})
    subject = email_template.get("subject", "新サービスのご案内")
    body_template = email_template.get("body", "")

    if dry_run:
        print(f"[GmailOutreach] DRY RUN: {len(target_emails)}件のメール送信予定")
        print(f"  件名: {subject}")
        return [{"success": True, "dry_run": True, "to": e} for e in target_emails]

    service = get_gmail_service()
    results = []

    for email_addr in target_emails[:5]:  # 1回の実行で最大5件
        # プレースホルダーを置き換え
        body = body_template.replace("[会社名]", "御社").replace("[担当者名]", "担当者様")

        if service:
            result = send_email(service, email_addr, subject, body)
        else:
            # Gmail API未設定 → ドラフト保存
            result = save_outreach_draft(
                email_addr, subject, body,
                f"SaaS: {idea.get('name', '')}"
            )

        result["to"] = email_addr
        result["sent_at"] = datetime.now().isoformat()
        results.append(result)

        import time
        time.sleep(3)  # 送信間隔

    return results
