#!/usr/bin/env python3
"""產生交付檔名並記帳 —— 檔名由規則產生,不准手取。

    uv run python tools/deliver.py <案名> <說明> [--label 簡稱] [--final] [--send]

交付檔名:

    <簡稱>_<解析度>_V<序號>_<說明>_<YYYYMMDD>_<HHMMSS>.mp4
    圖書館_480p_V2_新順序_20260811_142655.mp4

五個欄位缺一不可,理由各自不同:
  簡稱      同一時間可能有好幾案在跑,光看「480p預覽」不知道是誰
  解析度    480p 是給業主看版面的、4K 才是交片,混在一起會寄錯
  V序號     「哪一版」的唯一答案;日期時間排序看得出先後,但講不出「第幾版」
  說明      V2 到底改了什麼,不用回頭翻 CHANGELOG
  日期+時間 同一天必然會有好幾版(24 小時制)。**時間取自渲染輸出檔本身**,
            不是複製當下 —— 複製時間會隨手滑掉,渲染時間才是這個版本的身分。

⚠️ 為什麼要有這支工具:手工取名兩次就會漂成兩種格式,而且人重取名時
   幾乎一定會把時間砍掉只留日期。管線內部一直有正確時間戳 ——
   「複製給人」那一步才是資訊流失的地方。手取名 = 遲早會漂。

序號記在案件夾的 `交付紀錄.md`(同時也是「V2 對應哪支渲染檔」的唯一答案)。

`--send` 會跑環境變數 `VIDEOMAKER_SEND_CMD` 指定的送檔指令(收一個參數:檔案路徑);
沒設就只印路徑,不當機。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
JOBS = REPO / "jobs"
LEDGER = "交付紀錄.md"

# `--send` 要跑的送檔指令。收一個參數:交付檔的絕對路徑。
# 環境變數沒設就不送 —— 只印出檔案位置,不當機(別人的機器沒有這支腳本)。
SEND_CMD = os.environ.get("VIDEOMAKER_SEND_CMD", "")

# 渲染輸出的檔名格式(videomaker/render.py 產的):preview_20260806-142655.mp4
_RE_RENDER = re.compile(r"^(preview|final)_(\d{8})-(\d{6})\.mp4$")
_RE_ROW = re.compile(r"^\|\s*V(\d+)\s*\|")


def resolution_label(path: Path) -> str:
    """用實際畫面高度講人話,不猜。"""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    h = json.loads(out.stdout)["streams"][0]["height"]
    return {480: "480p", 720: "720p", 1080: "1080p", 1440: "1440p", 2160: "4K"}.get(h, f"{h}p")


def latest_render(out_dir: Path, kind: str) -> Path:
    """最新的一支渲染實體檔(symlink 不算——它只是指標,沒有自己的時間戳)。"""
    cands = [p for p in out_dir.iterdir() if not p.is_symlink() and _RE_RENDER.match(p.name)
             and _RE_RENDER.match(p.name).group(1) == kind]
    if not cands:
        raise SystemExit(f"❌ {out_dir} 裡沒有 {kind}_YYYYMMDD-HHMMSS.mp4,先跑 render")
    return max(cands, key=lambda p: p.name)


def read_ledger(path: Path) -> tuple[int, str | None]:
    """回傳 (目前最大版號, 上次用的簡稱)。沒有紀錄就 (0, None)。"""
    if not path.exists():
        return 0, None
    top_v, label = 0, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if m := _RE_ROW.match(line):
            top_v = max(top_v, int(m.group(1)))
            if label is None:  # 最新在上,第一筆就是最近用的簡稱
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) >= 5 and "_" in cells[4]:
                    label = cells[4].split("_")[0]
    return top_v, label


def write_ledger(path: Path, row: str) -> None:
    header = (
        "# 交付紀錄\n\n"
        "> 由 `tools/deliver.py` 產生,**不要手改**。檔名規則見該檔 docstring。\n"
        "> 這張表是「V幾 = 哪支渲染檔」的唯一答案。最新在上。\n\n"
        "| 版本 | 說明 | 交付時間 | 來源渲染檔 | 交付檔名 |\n"
        "|---|---|---|---|---|\n"
    )
    if not path.exists():
        path.write_text(header + row + "\n", encoding="utf-8")
        return
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    at = next((i for i, ln in enumerate(lines) if ln.startswith("|---")), len(lines) - 1) + 1
    path.write_text("".join(lines[:at] + [row + "\n"] + lines[at:]), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="產生合規的交付檔名並記進交付紀錄")
    ap.add_argument("job", help="案名(jobs/ 底下的資料夾名)")
    ap.add_argument("note", help="這一版改了什麼,2–4 個字,例:初版 / 新順序 / 補英文")
    ap.add_argument("--label", help="檔名開頭的簡稱;省略 = 沿用上次(第一次交付必填)")
    ap.add_argument("--final", action="store_true", help="交付 final_*(預設交付 preview_*)")
    ap.add_argument("--send", action="store_true",
                    help="產完順便跑 $VIDEOMAKER_SEND_CMD 送檔(沒設就只印路徑)")
    ap.add_argument("--render", help="指定要交付哪支渲染檔(省略 = 最新那支)")
    a = ap.parse_args()

    job_dir = (JOBS / a.job).resolve()
    if not job_dir.is_dir():
        raise SystemExit(f"❌ 找不到案子:{JOBS / a.job}")
    out_dir = job_dir / "output"

    src = (out_dir / a.render).resolve() if a.render else latest_render(out_dir, "final" if a.final else "preview")
    m = _RE_RENDER.match(src.name)
    if not m:
        raise SystemExit(f"❌ {src.name} 不是渲染輸出檔名(要 preview/final_YYYYMMDD-HHMMSS.mp4)")
    _, date, time = m.groups()

    ledger = job_dir / LEDGER
    last_v, last_label = read_ledger(ledger)
    label = a.label or last_label
    if not label:
        raise SystemExit("❌ 這案還沒交付過,請用 --label 給簡稱(例:--label 圖書館)")

    name = f"{label}_{resolution_label(src)}_V{last_v + 1}_{a.note}_{date}_{time}.mp4"
    dest = out_dir / name
    if dest.exists():
        raise SystemExit(f"❌ {name} 已存在,不覆蓋")
    # 交付檔是硬連結:同一份資料、兩個名字,不佔第二份空間也不會走味
    dest.hardlink_to(src)

    write_ledger(ledger, (
        f"| V{last_v + 1} | {a.note} | {datetime.now().astimezone():%Y-%m-%d %H:%M} "
        f"| {src.name} | {name} |"
    ))
    print(f"✅ V{last_v + 1}:{name}\n   ← {src.name}\n   紀錄:{ledger}")

    if a.send:
        if not SEND_CMD:
            print("ℹ️  沒設 VIDEOMAKER_SEND_CMD,不送檔。交付檔在上面那個路徑,自己拿。")
            return 0
        if not Path(SEND_CMD).exists():
            print(f"⚠️  VIDEOMAKER_SEND_CMD 指到 {SEND_CMD},但那個檔不存在。沒送出。")
            return 1
        r = subprocess.run([SEND_CMD, str(dest), "--copy"], check=False)
        return r.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
