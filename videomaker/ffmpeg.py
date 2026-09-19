"""ffmpeg/ffprobe subprocess 包裝。失敗保留 stderr 尾段,不靜默。"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


class FfmpegError(RuntimeError):
    pass


def run(cmd: list[str], cwd: Path | None = None) -> None:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.splitlines()[-15:])
        raise FfmpegError(f"指令失敗:{' '.join(cmd[:8])} …\n--- stderr 尾段 ---\n{tail}")


def probe(path: Path) -> dict:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_streams", "-show_format", str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise FfmpegError(f"ffprobe 失敗:{path}\n{proc.stderr[-500:]}")
    return json.loads(proc.stdout)


@dataclass
class VideoInfo:
    width: int
    height: int
    fps: str  # 保留分數字串如 "30000/1001"
    duration: float
    has_audio: bool


def video_info(path: Path) -> VideoInfo:
    data = probe(path)
    vstream = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if vstream is None:
        raise FfmpegError(f"{path} 沒有 video stream")
    has_audio = any(s["codec_type"] == "audio" for s in data["streams"])
    duration = float(data["format"].get("duration") or vstream.get("duration") or 0)
    return VideoInfo(
        width=int(vstream["width"]),
        height=int(vstream["height"]),
        fps=vstream.get("avg_frame_rate") or vstream.get("r_frame_rate") or "30",
        duration=duration,
        has_audio=has_audio,
    )


def fit_filter(w: int, h: int, fit: str = "contain") -> str:
    """把任何比例的來源塞進 w×h 的濾鏡片段(渲染與 Studio 靜態排版共用同一條)。

    contain = 整張縮進畫面、四周補黑(素材完整,但比例不同的段落會有黑邊)
    cover   = 放大到蓋滿再中心裁切(滿版無黑邊,超出的上下/左右被切掉)

    這條必須是**唯一**來源:預覽用 contain、成品用 cover 的話,
    Studio 裡看到的排版就不是成品的排版(靜態排版模式的意義就沒了)。
    """
    if fit == "cover":
        return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"
    )


@lru_cache(maxsize=1)
def pick_encoder() -> str:
    """優先 Mac 硬體編碼,失敗退 libx264。"""
    test = [
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=0.1",
        "-c:v", "h264_videotoolbox", "-f", "null", "-",
    ]
    proc = subprocess.run(test, capture_output=True, check=False)
    return "h264_videotoolbox" if proc.returncode == 0 else "libx264"
