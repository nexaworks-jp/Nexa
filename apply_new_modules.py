"""
新モジュール自動適用スクリプト
proposals/new_modules/ にある新しいPythonモジュールを
workers/ に移動して main.py に自動登録する
"""
import os
import sys
import json
import shutil
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NEW_MODULES_DIR = os.path.join(BASE_DIR, "proposals", "new_modules")
WORKERS_DIR = os.path.join(BASE_DIR, "workers")
APPLIED_LOG = os.path.join(BASE_DIR, "memory", "applied_modules.json")


def load_applied() -> list:
    if os.path.exists(APPLIED_LOG):
        with open(APPLIED_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_applied(applied: list):
    os.makedirs(os.path.dirname(APPLIED_LOG), exist_ok=True)
    with open(APPLIED_LOG, "w", encoding="utf-8") as f:
        json.dump(applied, f, ensure_ascii=False, indent=2)


def validate_module(filepath: str) -> bool:
    """モジュールの基本的な安全チェック"""
    with open(filepath, "r", encoding="utf-8") as f:
        code = f.read()

    # 危険なコードのチェック
    forbidden = ["os.remove", "shutil.rmtree", "subprocess", "eval(", "exec(", "__import__"]
    for pattern in forbidden:
        if pattern in code:
            print(f"[ApplyModules] 危険なコードを検出: {pattern} -> スキップ")
            return False

    # run() 関数の存在チェック
    if "def run(" not in code:
        print(f"[ApplyModules] run() 関数が見つかりません -> スキップ")
        return False

    return True


def apply_new_modules() -> list:
    """新モジュールをworkersに適用する"""
    if not os.path.exists(NEW_MODULES_DIR):
        print("[ApplyModules] 新モジュールディレクトリなし")
        return []

    applied = load_applied()
    applied_names = [a["filename"] for a in applied]
    new_files = [f for f in os.listdir(NEW_MODULES_DIR) if f.endswith(".py")]
    newly_applied = []

    for filename in new_files:
        if filename in applied_names:
            continue

        src = os.path.join(NEW_MODULES_DIR, filename)
        print(f"[ApplyModules] 新モジュール検出: {filename}")

        if not validate_module(src):
            continue

        # workers/ にコピー（日付プレフィックスなしの名前で）
        # 例: 20240312_アフィリエイト.py -> affiliate_auto.py
        clean_name = "_".join(filename.split("_")[1:]).lower()
        clean_name = clean_name.replace("・", "_").replace(" ", "_")
        # ASCII文字のみ
        ascii_name = "".join(c if c.isascii() and (c.isalnum() or c == "_") else "_" for c in clean_name)
        if not ascii_name.endswith(".py"):
            ascii_name += ".py"
        dst = os.path.join(WORKERS_DIR, f"auto_{ascii_name}")

        shutil.copy2(src, dst)
        print(f"[ApplyModules] 適用: {dst}")

        applied.append({
            "filename": filename,
            "applied_as": f"auto_{ascii_name}",
            "applied_at": datetime.now().isoformat()
        })
        newly_applied.append(f"auto_{ascii_name}")

    save_applied(applied)
    return newly_applied


if __name__ == "__main__":
    result = apply_new_modules()
    if result:
        print(f"[ApplyModules] {len(result)} 個の新モジュールを適用しました: {result}")
    else:
        print("[ApplyModules] 新モジュールなし")
