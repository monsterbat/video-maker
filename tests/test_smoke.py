"""最小冒煙測試:環境與入口活著。"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_ffmpeg_available():
    assert shutil.which("ffmpeg"), "ffmpeg 不在 PATH"
    assert shutil.which("ffprobe"), "ffprobe 不在 PATH"


def test_cli_help():
    result = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "render" in result.stdout
