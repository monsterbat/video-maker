#!/usr/bin/env python3
"""重建示範案 `jobs/_demo` —— 全合成素材,零真實客戶資料。

    uv run python tools/make_demo.py [--force]

**為什麼要有這支工具(2026-08-11):**
原本的 `_demo` 是直接拿一個真實案子來當 fixture ——
案名、業主機關、13 句字幕全是真的,而且測試裡還寫死了業主的案名。
它同時被 `.gitignore` 的 `jobs/` 擋住沒進 repo,於是造成兩個問題:
  ① 別人 clone 下來 `make check` 直接 8 紅(fixture 不存在)
  ② 想讓它進 repo,又等於把客戶資料公開

兩個問題一起解:**示範案改成完全虛構、素材用 ffmpeg 當場合成**。
案名「範例縣立圖書館新建工程」與所有單位名都是編的,影片是漸層色塊,
音樂是合成和弦,LOGO 是 Pillow 畫的。全部加起來約 1.5MB,可以安心進 git。

素材是「生成的」不是「收藏的」——所以這支工具才是正本,
`jobs/_demo/` 底下的檔案隨時可以砍掉重建。
"""

from __future__ import annotations

import argparse
import math
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "jobs" / "_demo"

# 13 個機位:虛構的圖書館走察。顏色由冷到暖,方便一眼看出順序有沒有跑掉。
CLIPS = [
    ("校園入口至圖書館模擬圖", "Simulated view from the campus entrance to the library", "左下", "白"),
    ("圖書館正立面模擬圖", "Simulated front elevation of the library", "右下", "白"),
    ("前側遮陽格柵細節模擬圖", "Simulated detail of the front sunshade louvers", "右下", "白"),
    ("入口門廊及停車場模擬圖", "Simulated entrance porch and parking area", "左下", "白"),
    ("側立面及周邊環境模擬圖", "Simulated side elevation and surrounding environment", "左下", "白"),
    ("後側庭園模擬圖", "Simulated rear garden", "左下", "黑"),
    ("中庭天井採光模擬圖", "Simulated daylighting of the central atrium", "右下", "黑"),
    ("圖書館背立面模擬圖", "Simulated rear elevation of the library", "右下", "黑"),
    ("門廳與閱覽區關係模擬圖", "Simulated relationship between lobby and reading area", "左下", "黑"),
    ("兒童閱覽室整體鳥瞰模擬圖", "Simulated aerial view of the children's reading room", "左下", "白"),
    ("階梯閱覽區及書牆模擬圖", "Simulated stepped reading area and book wall", "右下", "黑"),
    ("自習室整體模擬圖", "Simulated overall view of the study room", "右下", "黑"),
    ("屋頂平台至中庭整體關係模擬圖", "Simulated relationship from the roof deck to the atrium", "左下", "白"),
]

# 每支 clip 的漸層兩端色(冷 → 暖)
COLORS = [
    ("0x0d2137", "0x2e6f8e"), ("0x123049", "0x3f86a0"), ("0x17405b", "0x4f9ba8"),
    ("0x1d4f6c", "0x62aeaa"), ("0x245e73", "0x77bda9"), ("0x2d6c73", "0x8fc8a4"),
    ("0x3a7a6e", "0xa8d09f"), ("0x4d8567", "0xc0d69a"), ("0x648e5f", "0xd4d795"),
    ("0x7e9459", "0xe2cf8f"), ("0x9a9755", "0xecc088"), ("0xb69453", "0xf2ab81"),
    ("0xd08d54", "0xf5947c"),
]

CLIP_SECONDS = 3.0
W, H, FPS = 1280, 720, 30

BRIEF = """片頭黑幕1開始(1.5秒)
開始片頭顯示三行文字
範例縣立圖書館新建工程
新建工程委託規劃設計(暨後續擴充履約監造)
範例縣政府

片頭黑幕2 (2~3秒):文字(中文+英文+LOGO)

每個機位左上角放片頭2(中文+英文+LOGO)
{clip_lines}

結尾白幕1開始(1.5秒)
開始片頭顯示三行文字
範例縣立圖書館新建工程
新建工程委託規劃設計(暨後續擴充履約監造)
範例縣政府
結尾白幕2 (2~3秒):文字(中文+英文+LOGO)
"""


def build_brief() -> str:
    lines = [
        f"機位{i}文字:{pos}{color}字({zh})+下方英文字"
        for i, (zh, _en, pos, color) in enumerate(CLIPS, 1)
    ]
    return BRIEF.format(clip_lines="\n".join(lines))


def make_clips(dst: Path) -> None:
    """漸層色塊當假素材:看得出前後順序、壓縮後極小(每支 ~80KB)。"""
    dst.mkdir(parents=True, exist_ok=True)
    for i, (c0, c1) in enumerate(COLORS, 1):
        out = dst / f"{i:02d}.mp4"
        src = (
            f"gradients=s={W}x{H}:c0={c0}:c1={c1}:x0=0:y0=0:x1={W}:y1={H}"
            f":speed=0.05:d={CLIP_SECONDS}:r={FPS}"
        )
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", src,
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "30", str(out)],
            check=True,
        )
    print(f"  ✅ {len(COLORS)} 支 clip({W}x{H}@{FPS}, {CLIP_SECONDS}s)")


def make_music(path: Path) -> None:
    """合成一段平靜的和弦墊底。純 Python 寫 wav —— 不依賴 ffmpeg 有沒有編 mp3。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    rate, seconds = 22050, 50
    # A 大調的幾個音,慢慢輪替,避免聽起來像警報
    chords = [(220.0, 277.2, 329.6), (196.0, 246.9, 293.7),
              (174.6, 220.0, 261.6), (196.0, 261.6, 311.1)]
    frames = bytearray()
    for n in range(rate * seconds):
        t = n / rate
        chord = chords[int(t / 4) % len(chords)]
        v = sum(math.sin(2 * math.pi * f * t) for f in chord) / len(chord)
        v *= 0.35 * min(1.0, t / 2, (seconds - t) / 3)  # 淡入淡出,不要爆音
        frames += struct.pack("<h", int(max(-1.0, min(1.0, v)) * 32767))
    raw = path.with_suffix(".raw.wav")
    with wave.open(str(raw), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    # 轉 mp3:50 秒的 wav 是 2.1MB,進 git 太胖;mp3 只要 1/5
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-b:a", "64k", str(path)],
        check=True,
    )
    raw.unlink()
    print(f"  ✅ 配樂 {seconds}s({path.stat().st_size // 1024}KB)")


def make_logo(path: Path) -> None:
    """虛構事務所的 LOGO:白色線框方塊 + 字。透明底,和真案的 LOGO 同性質。"""
    from PIL import Image, ImageDraw, ImageFont

    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", (420, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([4, 20, 84, 100], outline=(255, 255, 255, 255), width=5)
    d.line([24, 44, 64, 44], fill=(255, 255, 255, 255), width=5)
    d.line([24, 60, 64, 60], fill=(255, 255, 255, 255), width=5)
    d.line([24, 76, 50, 76], fill=(255, 255, 255, 255), width=5)
    font_path = REPO / "fonts" / "NotoSansTC-Bold.otf"
    try:
        font = ImageFont.truetype(str(font_path), 40)
    except OSError:
        font = ImageFont.load_default()
    d.text((104, 38), "範例建築師事務所", font=font, fill=(255, 255, 255, 255))
    img.save(path)
    print(f"  ✅ LOGO({path.stat().st_size // 1024}KB)")


def main() -> int:
    ap = argparse.ArgumentParser(description="重建全虛構的示範案 jobs/_demo")
    ap.add_argument("--force", action="store_true", help="已存在也重做")
    a = ap.parse_args()

    if DEMO.exists() and not a.force:
        sys.exit(f"{DEMO} 已存在。要重建請加 --force")

    print(f"重建示範案:{DEMO}")
    # 先清空:不然改了素材格式(例 wav→mp3)舊檔會留下來,體積默默變兩倍
    if DEMO.exists():
        shutil.rmtree(DEMO)
    make_clips(DEMO / "input" / "clips")
    make_music(DEMO / "input" / "audio" / "bgm.mp3")
    make_logo(DEMO / "input" / "assets" / "logo.png")

    brief = DEMO / "brief.txt"
    brief.write_text(build_brief(), encoding="utf-8")
    print("  ✅ brief.txt(業主原文格式,虛構內容)")

    # 用真正的解析器產 job.yaml —— 示範案順便當成 parse_brief 的活體驗證
    sys.path.insert(0, str(REPO))
    from videomaker.parse_brief import parse_brief
    from videomaker.spec import save_job

    spec, warnings = parse_brief(brief.read_text(encoding="utf-8"), job_dir=DEMO)
    spec.audio.music = "input/audio/bgm.mp3"
    # 業主 brief 從來不含英文內文(真案也是),這裡直接補上,示範案要能一次跑到底
    for clip, (_zh, en, _p, _c) in zip(spec.clips, CLIPS, strict=True):
        clip.caption.text_en = en
    save_job(spec, DEMO / "job.yaml")
    print(f"  ✅ job.yaml(機位 {len(spec.clips)} 個,解析警告 {len(warnings)} 則)")

    total = sum(p.stat().st_size for p in DEMO.rglob("*") if p.is_file())
    print(f"\n完成:{total / 1024 / 1024:.1f}MB")
    print("驗證:uv run python main.py render _demo --preview")
    return 0


if __name__ == "__main__":
    sys.exit(main())
