"""VideoMaker Studio 後端(port 8020)。

啟動:make studio(= uv run uvicorn server:app --host 127.0.0.1 --port 8020)
渲染走子程序跑 main.py(與 CLI 同一條路),進度靠 log 檔輪詢。
"""

from __future__ import annotations

import io
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from videomaker import ffmpeg, textimg
from videomaker.spec import load_job, save_job, spec_from_dict

ROOT = Path(__file__).resolve().parent
JOBS = ROOT / "jobs"
FONTS = ROOT / "fonts"

app = FastAPI(title="VideoMaker Studio")

_renders: dict[str, dict] = {}  # 案名 → {proc, log, kind}


def _job_dir(name: str) -> Path:
    d = JOBS / name
    if not d.is_dir() or d.name.startswith("."):
        raise HTTPException(404, f"找不到案件 {name}")
    return d


@app.get("/api/jobs")
def list_jobs():
    out = []
    if JOBS.is_dir():
        for d in sorted(JOBS.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                out.append({
                    "name": d.name,
                    "has_job": (d / "job.yaml").exists(),
                    "has_brief": (d / "brief.txt").exists(),
                    "has_preview": (d / "output/preview.mp4").exists(),
                    "has_final": (d / "output/final.mp4").exists(),
                })
    return out


@app.get("/api/jobs/{name}")
def get_job(name: str):
    d = _job_dir(name)
    if not (d / "job.yaml").exists():
        raise HTTPException(404, "還沒有 job.yaml,先跑 parse")
    spec = load_job(d / "job.yaml")
    clips = []
    for i, clip in enumerate(spec.clips, start=1):
        p = d / clip.file
        duration = None
        if p.exists():
            try:
                duration = ffmpeg.video_info(p).duration
            except ffmpeg.FfmpegError:
                pass
        clips.append({"index": i, "exists": p.exists(), "duration": duration})
    music_duration = None
    if spec.audio.music and (d / spec.audio.music).exists():
        music_duration = float(ffmpeg.probe(d / spec.audio.music)["format"]["duration"])
    return {
        "spec": asdict(spec),
        "clips_probe": clips,
        "music_duration": music_duration,
        "has_preview": (d / "output/preview.mp4").exists(),
        "has_final": (d / "output/final.mp4").exists(),
    }


@app.put("/api/jobs/{name}")
def put_job(name: str, body: dict):
    d = _job_dir(name)
    spec = spec_from_dict(body)
    problems = spec.validate()
    if problems:
        raise HTTPException(400, ";".join(problems))
    save_job(spec, d / "job.yaml")
    return {"ok": True}


@app.post("/api/jobs/{name}/thumbs")
def make_thumbs(name: str):
    """每個機位抽第一幀當時間軸縮圖(320 寬,已存在就跳過)。"""
    d = _job_dir(name)
    spec = load_job(d / "job.yaml")
    thumbs_dir = d / "output/thumbs"
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    for i, clip in enumerate(spec.clips, start=1):
        src = d / clip.file
        thumb = thumbs_dir / f"seg_{i:02d}.jpg"
        if src.exists() and not thumb.exists():
            ffmpeg.run([
                "ffmpeg", "-y", "-v", "error", "-i", str(src),
                "-frames:v", "1", "-vf", "scale=320:-2", str(thumb),
            ])
        if thumb.exists():
            out[i] = f"/files/{name}/output/thumbs/seg_{i:02d}.jpg"
    return out


@app.post("/api/jobs/{name}/overlay")
def overlay_preview(name: str, body: dict):
    """即時疊層:用「還沒存檔的 spec」畫出字幕/卡片 PNG,前端疊在影片上。
    純 Pillow,<0.1 秒——文字類改動不必渲染就能看效果。"""
    d = _job_dir(name)
    spec = spec_from_dict(body.get("spec") or {})
    kind = body.get("kind")
    w, h = 1280, 720  # 疊層固定 720p,夠看又快

    def existing(rel: str | None) -> Path | None:
        p = d / rel if rel else None
        return p if p and p.exists() else None

    if kind == "clip":
        index = int(body.get("index", 0))
        if not (1 <= index <= len(spec.clips)):
            raise HTTPException(400, "機位 index 超出範圍")
        img = textimg.caption_watermark_overlay(
            w, h, spec.style, spec.clips[index - 1].caption, spec.watermark,
            FONTS, existing(spec.watermark.logo) if spec.watermark else None,
            disclaimer=spec.disclaimer,
        )
    elif kind == "card":
        cards = spec.intro if body.get("group") == "intro" else spec.outro
        gi = int(body.get("gindex", 0))
        if not (0 <= gi < len(cards)):
            raise HTTPException(400, "卡片 index 超出範圍")
        card = cards[gi]
        img = textimg.card_frame(
            w, h, spec.style, card, FONTS,
            logo_path=existing(card.logo), image_path=existing(card.image),
        )
    else:
        raise HTTPException(400, "kind 要是 clip 或 card")

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png")


@app.post("/api/jobs/{name}/compose")
def compose_preview(name: str, body: dict):
    """靜態排版合成圖:背景幀 + 疊層在「伺服器端」合成單張 PNG 回傳。
    前端只是一張 <img>,排版不會因 CSS 或黑邊跑位,看靜態圖就知道成品長怎樣。"""
    d = _job_dir(name)
    spec = spec_from_dict(body.get("spec") or {})
    kind = body.get("kind")
    w, h = 1280, 720

    def existing(rel: str | None) -> Path | None:
        p = d / rel if rel else None
        return p if p and p.exists() else None

    if kind == "clip":
        index = int(body.get("index", 0))
        if not (1 <= index <= len(spec.clips)):
            raise HTTPException(400, "機位 index 超出範圍")
        clip = spec.clips[index - 1]
        base = _clip_frame(d, clip.file, clip.start, w, h, spec.output.fit)
        overlay = textimg.caption_watermark_overlay(
            w, h, spec.style, clip.caption, spec.watermark,
            FONTS, existing(spec.watermark.logo) if spec.watermark else None,
            disclaimer=spec.disclaimer,
        )
        base.alpha_composite(overlay)
        img = base
    elif kind == "card":
        cards = spec.intro if body.get("group") == "intro" else spec.outro
        gi = int(body.get("gindex", 0))
        if not (0 <= gi < len(cards)):
            raise HTTPException(400, "卡片 index 超出範圍")
        card = cards[gi]
        img = textimg.card_frame(
            w, h, spec.style, card, FONTS,
            logo_path=existing(card.logo), image_path=existing(card.image),
        )
    else:
        raise HTTPException(400, "kind 要是 clip 或 card")

    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=90)
    return Response(buf.getvalue(), media_type="image/jpeg")


def _clip_frame(d: Path, rel: str, start: float, w: int, h: int, fit: str = "contain"):
    """抽機位在修剪起點的那一幀當背景(快取:來源檔+起點+裝法沒變就重用)。"""
    from PIL import Image

    src = d / rel
    if not src.exists():
        return Image.new("RGBA", (w, h), (24, 26, 31, 255))
    cache = d / "output/thumbs" / f"frame_{src.stem}_{start:.1f}_{fit}.png"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists() or cache.stat().st_mtime < src.stat().st_mtime:
        ffmpeg.run([
            "ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", str(src),
            "-frames:v", "1",
            "-vf", ffmpeg.fit_filter(w, h, fit),
            str(cache),
        ])
    return Image.open(cache).convert("RGBA")


@app.get("/api/jobs/{name}/waveform")
def waveform(name: str):
    """整首音樂的波形圖(快取;音樂檔換了才重畫)。"""
    d = _job_dir(name)
    spec = load_job(d / "job.yaml")
    music = d / spec.audio.music if spec.audio.music else None
    if not music or not music.exists():
        raise HTTPException(404, "沒有音樂檔")
    out = d / "output/waveform.png"
    if not out.exists() or out.stat().st_mtime < music.stat().st_mtime:
        out.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg.run([
            "ffmpeg", "-y", "-v", "error", "-i", str(music),
            "-filter_complex",
            "aformat=channel_layouts=mono,showwavespic=s=2400x140:colors=#5fa8ff",
            "-frames:v", "1", str(out),
        ])
    return FileResponse(out)


@app.post("/api/jobs/{name}/render")
def start_render(name: str, body: dict):
    d = _job_dir(name)
    running = _renders.get(name)
    if running and running["proc"].poll() is None:
        raise HTTPException(409, "這個案子正在渲染中")
    preview = bool(body.get("preview"))
    log = d / "output/render.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "main.py", "render", name] + (["--preview"] if preview else [])
    with open(log, "w") as log_file:  # Popen 繼承 fd,父程序這頭關掉沒關係
        proc = subprocess.Popen(
            cmd, cwd=ROOT, stdout=log_file, stderr=subprocess.STDOUT, text=True
        )
    _renders[name] = {"proc": proc, "log": log, "kind": "preview" if preview else "final"}
    return {"started": True, "kind": _renders[name]["kind"]}


@app.get("/api/jobs/{name}/render/status")
def render_status(name: str):
    d = _job_dir(name)
    entry = _renders.get(name)
    if entry is None:
        return {"running": False, "returncode": None, "log": ""}
    code = entry["proc"].poll()
    log_text = entry["log"].read_text(encoding="utf-8") if entry["log"].exists() else ""
    return {
        "running": code is None,
        "returncode": code,
        "kind": entry["kind"],
        "log": "\n".join(log_text.splitlines()[-25:]),
        "has_preview": (d / "output/preview.mp4").exists(),
        "has_final": (d / "output/final.mp4").exists(),
    }


@app.post("/api/jobs/{name}/export-fcpxml")
def export(name: str):
    from videomaker.fcpxml import export_fcpxml

    d = _job_dir(name)
    spec = load_job(d / "job.yaml")
    out = export_fcpxml(d, spec, d / "output" / f"{name}.fcpxml")
    return {"path": str(out), "url": f"/files/{name}/output/{name}.fcpxml"}


@app.get("/")
def index():
    return FileResponse(ROOT / "static/index.html")


# follow_symlink:案件實體可以放在 repo 外、jobs/ 只放 symlink(程式/資料分離)
app.mount("/files", StaticFiles(directory=JOBS, follow_symlink=True), name="files")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
# docs/ 只在完整版裡有;資料夾不存在時不掛載,避免伺服器啟動失敗
if (ROOT / "docs").is_dir():
    app.mount("/docs", StaticFiles(directory=ROOT / "docs"), name="docs")
