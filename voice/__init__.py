# voice/ — TTSエンジン抽象レイヤー
# 将来的に engine= で別エンジンに差し替え可能
from .engine import TTSEngine, speak, synthesize
