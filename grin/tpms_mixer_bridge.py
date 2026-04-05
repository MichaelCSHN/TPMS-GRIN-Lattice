"""
从仓库根目录加载 TPMS_Mixer_v1.1.0.py（不修改该文件），供 grin 复用隐式场与 STL 写入。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_MIXER_PATH = _ROOT / "TPMS_Mixer_v1.1.0.py"


def load_mixer():
    if not _MIXER_PATH.is_file():
        raise FileNotFoundError(f"未找到 TPMS 主程序: {_MIXER_PATH}")
    spec = importlib.util.spec_from_file_location("tpms_mixer_v110", _MIXER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError("无法加载 TPMS_Mixer_v1.1.0 模块")
    mod = importlib.util.module_from_spec(spec)
    # 必须先注册，否则 TPMS_Mixer 内 @dataclass 解析类型注解会失败
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_mixer = None


def get_mixer():
    global _mixer
    if _mixer is None:
        _mixer = load_mixer()
    return _mixer
