"""FCPXML 匯出:把機位影片依序排上時間軸 + 音樂軌,給 Final Cut Pro 當微調草稿。

誠實界線(DESIGN §一 Phase 3 保險出口):只排「素材順序 + 時長 + 音樂」。
轉場請在 FCP 全選後 Cmd+T 一鍵補;字卡/字幕不匯出(FCP 的字幕引擎與本管線不相通)。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from . import ffmpeg
from .spec import JobSpec


def _t(seconds: float, fps: int = 60) -> str:
    """秒 → FCPXML 有理數時間,對齊幀界。"""
    frames = round(seconds * fps)
    return f"{frames * 100}/{fps * 100}s"


def export_fcpxml(job_dir: Path, spec: JobSpec, out_path: Path) -> Path:
    root = ET.Element("fcpxml", version="1.9")
    resources = ET.SubElement(root, "resources")

    first = ffmpeg.video_info(job_dir / spec.clips[0].file)
    fps = round(eval_fps(first.fps))
    fmt = ET.SubElement(
        resources, "format", id="r1",
        frameDuration=f"100/{fps * 100}s",
        width=str(first.width), height=str(first.height),
    )
    if (first.width, first.height, fps) == (3840, 2160, 60):
        fmt.set("name", "FFVideoFormat3840x2160p60")

    clips = []
    for i, clip in enumerate(spec.clips, start=1):
        src = job_dir / clip.file
        info = ffmpeg.video_info(src)
        asset_id = f"a{i}"
        asset = ET.SubElement(
            resources, "asset", id=asset_id,
            name=src.stem, start="0s", duration=_t(info.duration, fps),
            hasVideo="1", hasAudio="1" if info.has_audio else "0", format="r1",
        )
        ET.SubElement(asset, "media-rep", kind="original-media", src=src.resolve().as_uri())
        clips.append((asset_id, src.stem, info.duration))

    music = None
    if spec.audio.music and (job_dir / spec.audio.music).exists():
        src = (job_dir / spec.audio.music).resolve()
        info = ffmpeg.probe(src)
        dur = float(info["format"]["duration"])
        asset = ET.SubElement(
            resources, "asset", id="music", name=src.stem,
            start="0s", duration=_t(dur, fps), hasAudio="1", hasVideo="0",
        )
        ET.SubElement(asset, "media-rep", kind="original-media", src=src.as_uri())
        music = dur

    total = sum(d for _, _, d in clips)
    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", name="VideoMaker")
    project = ET.SubElement(event, "project", name=spec.project or job_dir.name)
    sequence = ET.SubElement(
        project, "sequence", format="r1", duration=_t(total, fps),
        tcStart="0s", audioLayout="stereo", audioRate="48k",
    )
    spine = ET.SubElement(sequence, "spine")

    offset = 0.0
    for i, (asset_id, name, dur) in enumerate(clips):
        el = ET.SubElement(
            spine, "asset-clip", ref=asset_id, name=name,
            offset=_t(offset, fps), duration=_t(dur, fps), format="r1",
        )
        if i == 0 and music is not None:
            ET.SubElement(
                el, "asset-clip", ref="music", name="音樂", lane="-1",
                offset="0s", duration=_t(min(music, total), fps),
            )
        offset += dur

    ET.indent(root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n'
        + ET.tostring(root, encoding="unicode"),
        encoding="utf-8",
    )
    return out_path


def eval_fps(fps: str) -> float:
    num, _, den = fps.partition("/")
    return float(num) / float(den or 1)
