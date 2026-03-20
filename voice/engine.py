"""
voice/engine.py — TTSエンジン抽象レイヤー

現在のバックエンド: VOICEVOX（冥鳴ひまり）
将来的な差し替え先候補: Style-Bert-VITS2, ElevenLabs, AivisSpeech など

差し替え方法:
  1. 新エンジンのクラスを TTSEngine を継承して作成（または同インターフェースを持つ関数を実装）
  2. create_engine() の中身を差し替える
  3. voice/__init__.py は変更不要
"""

from __future__ import annotations
import io
import subprocess
import tempfile
import os
from abc import ABC, abstractmethod
from typing import Optional


class TTSEngine(ABC):
    """TTSエンジンの基底クラス。差し替え時はこれを継承する。"""

    @abstractmethod
    def synthesize(self, text: str) -> bytes:
        """テキストをWAV音声バイト列に変換する。"""
        ...

    def speak(self, text: str) -> None:
        """テキストを音声再生する（内部でsynthesizeを使用）。"""
        audio = self.synthesize(text)
        _play_audio(audio)


# ─────────────────────────────────────────────
# VOICEVOX実装（一時的。将来ここを差し替える）
# ─────────────────────────────────────────────

import requests

VOICEVOX_BASE_URL = "http://localhost:50021"
VOICEVOX_SPEAKER_ID = 14  # 冥鳴ひまり（ノーマル）


class VoicevoxEngine(TTSEngine):
    """
    VOICEVOXバックエンド。
    VOICEVOXがローカルで起動している必要がある。
    将来的にStyle-Bert-VITS2等に差し替え予定。
    """

    def __init__(
        self,
        base_url: str = VOICEVOX_BASE_URL,
        speaker_id: int = VOICEVOX_SPEAKER_ID,
    ):
        self.base_url = base_url
        self.speaker_id = speaker_id

    def synthesize(self, text: str) -> bytes:
        for attempt in range(3):
            try:
                # Step1: audio_query でクエリ生成
                query_resp = requests.post(
                    f"{self.base_url}/audio_query",
                    params={"text": text, "speaker": self.speaker_id},
                    timeout=20,
                )
                query_resp.raise_for_status()

                # Step2: synthesis で音声生成（文節間の無音を最小化）
                query = query_resp.json()
                query["prePhonemeLength"] = 0.05
                query["postPhonemeLength"] = 0.05
                audio_resp = requests.post(
                    f"{self.base_url}/synthesis",
                    params={"speaker": self.speaker_id},
                    json=query,
                    timeout=60,
                )
                audio_resp.raise_for_status()
                return audio_resp.content
            except requests.exceptions.Timeout:
                if attempt == 2:
                    raise
                import time
                time.sleep(1)
        raise RuntimeError("VOICEVOX synthesis failed after 3 attempts")


# ─────────────────────────────────────────────
# ファクトリー関数
# ─────────────────────────────────────────────

def create_engine() -> TTSEngine:
    """
    現在使用するTTSエンジンを返す。
    将来の差し替えはここだけ変更する。
    """
    return VoicevoxEngine()


# シングルトンインスタンス（モジュールロード時に生成）
_engine: Optional[TTSEngine] = None


def _get_engine() -> TTSEngine:
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


# ─────────────────────────────────────────────
# 公開API（エンジン非依存）
# ─────────────────────────────────────────────

def synthesize(text: str, engine: Optional[TTSEngine] = None) -> bytes:
    """テキストをWAVバイト列に変換する。"""
    return (engine or _get_engine()).synthesize(text)


def speak(text: str, engine: Optional[TTSEngine] = None) -> None:
    """テキストを音声再生する。"""
    (engine or _get_engine()).speak(text)


# ─────────────────────────────────────────────
# 音声再生ユーティリティ（Windows対応）
# ─────────────────────────────────────────────

def _play_audio(wav_bytes: bytes) -> None:
    """WAVバイト列を再生する（一時ファイル経由）。"""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        tmp_path = f.name
    try:
        if os.name == "nt":
            # Windows: PowerShellで再生（依存なし）
            subprocess.run(
                [
                    "powershell",
                    "-c",
                    f"(New-Object Media.SoundPlayer '{tmp_path}').PlaySync()",
                ],
                check=True,
            )
        else:
            # macOS / Linux
            player = "afplay" if os.uname().sysname == "Darwin" else "aplay"
            subprocess.run([player, tmp_path], check=True)
    finally:
        os.unlink(tmp_path)
