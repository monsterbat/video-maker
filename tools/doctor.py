#!/usr/bin/env python3
"""環境體檢 —— 跑不起來的時候,先跑這個。

    uv run python tools/doctor.py

檢查 Python / ffmpeg / 套件 / 字型 / 示範案,**缺什麼就直接講怎麼裝**,
而不是讓人去撞一個 traceback 再回頭 google。

⚠️ 這支刻意不依賴專案的任何套件(只用標準函式庫)——
   「套件沒裝好」正是它要診斷的情況之一,自己不能先掛掉。
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

OK, WARN, BAD = "✅", "⚠️ ", "❌"
_problems: list[str] = []
_warnings: list[str] = []


def say(mark: str, what: str, detail: str = "") -> None:
    print(f"  {mark} {what}" + (f" —— {detail}" if detail else ""))


def fail(what: str, detail: str, howto: str) -> None:
    say(BAD, what, detail)
    _problems.append(f"{what}\n     {howto}")


def warn(what: str, detail: str, howto: str = "") -> None:
    say(WARN, what, detail)
    _warnings.append(f"{what}:{detail}" + (f"\n     {howto}" if howto else ""))


def check_python() -> None:
    v = sys.version_info
    if (v.major, v.minor) >= (3, 11):
        say(OK, f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        fail(
            f"Python {v.major}.{v.minor}",
            "需要 3.11 以上",
            "uv 會自己裝對的版本:uv sync",
        )


def check_uv() -> None:
    if path := shutil.which("uv"):
        try:
            out = subprocess.run([path, "--version"], capture_output=True, text=True,
                                 check=True, timeout=10).stdout.strip()
            say(OK, out)
        except (subprocess.SubprocessError, OSError):
            warn("uv", "裝了但叫不動")
    else:
        fail("uv 沒裝", "這個專案用 uv 管套件與虛擬環境",
             "macOS/Linux:curl -LsSf https://astral.sh/uv/install.sh | sh\n"
             "     Windows:powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\"")


def _ffmpeg_version(exe: str) -> str | None:
    try:
        out = subprocess.run([exe, "-version"], capture_output=True, text=True,
                             check=True, timeout=15).stdout
        return out.splitlines()[0] if out else None
    except (subprocess.SubprocessError, OSError):
        return None


def check_ffmpeg() -> None:
    install_hint = (
        "macOS:brew install ffmpeg\n"
        "     Ubuntu/Debian:sudo apt install ffmpeg\n"
        "     Windows:winget install Gyan.FFmpeg"
    )
    for exe in ("ffmpeg", "ffprobe"):
        if not shutil.which(exe):
            fail(f"{exe} 沒裝", "整條管線靠它,沒有它什麼都做不了", install_hint)
            return
    line = _ffmpeg_version("ffmpeg") or ""
    say(OK, line.split(" Copyright")[0] or "ffmpeg")

    # 必要濾鏡:少一個就出不了片
    try:
        filters = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                                 capture_output=True, text=True, check=True, timeout=20).stdout
    except (subprocess.SubprocessError, OSError):
        warn("ffmpeg 濾鏡", "查不到清單,跳過檢查")
        return
    missing = [f for f in ("xfade", "overlay", "scale", "pad", "crop") if f" {f} " not in filters]
    if missing:
        fail("ffmpeg 缺濾鏡", f"少了 {', '.join(missing)}",
             "換一個編譯比較完整的 ffmpeg(homebrew / 官方 static build 都可以)")
    else:
        say(OK, "ffmpeg 濾鏡齊全", "xfade / overlay / scale / pad / crop")

    # libass 不是必要的 —— 這個專案故意不走那條路,講清楚免得有人以為缺了東西
    if "ass" not in filters:
        say(OK, "沒有 libass(正常)", "本專案用 Pillow 畫 PNG 疊圖,不靠 drawtext/subtitles")


def check_packages() -> None:
    missing = []
    for mod, why in (("PIL", "畫字幕圖層"), ("yaml", "讀 job.yaml"),
                     ("fastapi", "Studio 網頁介面"), ("uvicorn", "Studio 伺服器")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(f"{mod}({why})")
    if missing:
        fail("Python 套件沒裝齊", "、".join(missing),
             "uv sync   ← 然後用 `uv run python …` 跑,不要直接 python")
    else:
        say(OK, "Python 套件齊全", "Pillow / PyYAML / FastAPI / uvicorn")


def check_fonts() -> None:
    fonts = REPO / "fonts"
    if not fonts.is_dir():
        fail("fonts/ 不存在", "沒有字型就畫不出中文字幕", "重新 clone,或自己放字型檔進去")
        return
    defaults = ["NotoSansTC-Regular.otf", "NotoSansTC-Bold.otf"]
    lack = [f for f in defaults if not (fonts / f).exists()]
    if lack:
        fail("預設字型不在", "、".join(lack),
             "job.yaml 的 style.font 改成 fonts/ 裡真的有的檔名,或補上這些檔")
    else:
        n = len(list(fonts.rglob("*.otf"))) + len(list(fonts.rglob("*.ttf")))
        say(OK, f"字型 {n} 個", "預設 Noto Sans TC 在位")


def check_demo() -> None:
    demo = REPO / "jobs" / "_demo"
    if not (demo / "job.yaml").exists():
        warn("示範案 jobs/_demo 不完整", "測試會失敗",
             "uv run python tools/make_demo.py --force")
        return
    clips = list((demo / "input" / "clips").glob("*.mp4")) if (demo / "input" / "clips").is_dir() else []
    if len(clips) < 13:
        warn("示範案素材不齊", f"只有 {len(clips)} 支 clip(應該 13 支)",
             "uv run python tools/make_demo.py --force")
    else:
        say(OK, "示範案 jobs/_demo 完整", "13 支 clip + 音樂 + LOGO")


def main() -> int:
    print(f"\nVideoMaker 環境體檢({platform.system()} {platform.machine()})\n")

    print("必要條件")
    check_python()
    check_uv()
    check_ffmpeg()
    check_packages()

    print("\n專案素材")
    check_fonts()
    check_demo()

    print()
    if _problems:
        print(f"{BAD} 有 {len(_problems)} 項要先解決:\n")
        for i, p in enumerate(_problems, 1):
            print(f"  {i}. {p}\n")
        return 1

    if _warnings:
        print(f"{WARN}{len(_warnings)} 項提醒(不影響出片):\n")
        for w in _warnings:
            print(f"  · {w}")
        print()

    print(f"{OK} 環境沒問題。試跑內建的虛構示範案:\n")
    print("     uv run python main.py render _demo --preview")
    print("     → jobs/_demo/output/preview.mp4(31 秒)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
