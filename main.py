"""VideoMaker CLI。用法見 README.md,規格見 DESIGN.md。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JOBS = ROOT / "jobs"
FONTS = ROOT / "fonts"

BRIEF_PLACEHOLDER = """\
(把業主給的整段文字貼進來,存檔後跑:uv run python main.py parse <案名>)
"""


def _job_dir(name: str) -> Path:
    d = JOBS / name
    if not d.is_dir():
        sys.exit(f"找不到案件:{d}\n先跑:uv run python main.py new {name}")
    return d


def load_brand() -> dict:
    """讀 brand.yaml(公司名/責任聲明/預設字型)。沒有或壞掉都不當機——它只是預設值。

    brand.yaml 是**各自本機的**(不進 git,不然每個人填自己的公司名會一直撞衝突);
    沒有的話退回 brand.example.yaml —— 裡面全是空值,等於「不套品牌」。
    """
    import yaml

    path = ROOT / "brand.yaml"
    if not path.exists():
        path = ROOT / "brand.example.yaml"
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        print(f"⚠️  {path.name} 讀不動,先跳過:{e}")
        return {}


def _apply_brand(spec, brand: dict) -> None:
    """把 brand.yaml 的公司預設值套進剛解析出來的 spec。

    只填「業主 brief 不會寫、但每一案都一樣」的東西(責任聲明、預設字型)。
    ⛔ 不覆蓋 brief 已經解析出來的內容 —— 業主寫的優先。
    """
    from videomaker.spec import Disclaimer

    disc = brand.get("disclaimer") or {}
    if (disc.get("text_zh") or disc.get("text_en")) and spec.disclaimer is None:
        spec.disclaimer = Disclaimer(
            text_zh=disc.get("text_zh", ""), text_en=disc.get("text_en", "")
        )
    fonts = brand.get("fonts") or {}
    if fonts.get("caption"):
        spec.style.font = fonts["caption"]
    if fonts.get("card"):
        spec.style.card_font = fonts["card"]
    if brand.get("fit") in ("contain", "cover"):
        spec.output.fit = brand["fit"]


def cmd_new(args) -> None:
    d = JOBS / args.name
    for sub in ("input/clips", "input/audio", "input/assets", "output"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    brief = d / "brief.txt"
    if not brief.exists():
        brief.write_text(BRIEF_PLACEHOLDER, encoding="utf-8")
    print(f"已建立 {d}")
    brand = load_brand()
    if brand.get("studio", {}).get("name_zh"):
        print(f"  (品牌預設:{brand['studio']['name_zh']} —— 來自 brand.yaml,parse 後會套進 job.yaml)")
    print("  1. 業主文字貼進 brief.txt")
    print("  2. 影片放 input/clips/(檔名排序 = 機位順序)")
    print("  3. 音樂放 input/audio/、LOGO 放 input/assets/logo.png")
    print(f"  4. uv run python main.py parse {args.name}")


def cmd_parse(args) -> None:
    from videomaker.parse_brief import parse_brief
    from videomaker.spec import save_job

    d = _job_dir(args.name)
    brief = d / "brief.txt"
    if not brief.exists():
        sys.exit(f"沒有 {brief},先把業主文字貼進去")
    out = d / "job.yaml"
    if out.exists() and not args.force:
        sys.exit(f"{out} 已存在(可能有手動微調)。要重新解析請加 --force")

    spec, warnings = parse_brief(brief.read_text(encoding="utf-8"), job_dir=d)
    # 音樂:input/audio/ 有檔就帶第一個
    audio_files = sorted(
        p for p in (d / "input/audio").glob("*")
        if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".aac", ".flac")
    )
    if audio_files:
        spec.audio.music = str(audio_files[0].relative_to(d))
    else:
        warnings.append("input/audio/ 沒有音樂檔,先出無音樂版本")

    _apply_brand(spec, load_brand())
    save_job(spec, out)
    print(f"✅ 已產生 {out}(機位 {len(spec.clips)} 個)")
    if warnings:
        print(f"\n⚠️ 需要人工確認的 {len(warnings)} 件事:")
        for w in warnings:
            print(f"  - {w}")
        print("\n改完 job.yaml 後跑:uv run python main.py render " + args.name)


def cmd_probe(args) -> None:
    from videomaker.ffmpeg import video_info
    from videomaker.spec import load_job

    d = _job_dir(args.name)
    spec = load_job(d / "job.yaml")
    print(f"{'檔案':<40}{'解析度':<12}{'fps':<14}{'長度':<8}聲音")
    base = None
    for clip in spec.clips:
        p = d / clip.file
        if not p.exists():
            print(f"{clip.file:<40}❌ 檔案不存在")
            continue
        info = video_info(p)
        flag = ""
        if base is None:
            base = info
        elif (info.width, info.height, info.fps) != (base.width, base.height, base.fps):
            flag = "  ⚠️ 與第一支規格不同"
        print(
            f"{clip.file:<40}{info.width}x{info.height:<7}{info.fps:<14}"
            f"{info.duration:<8.1f}{'有' if info.has_audio else '無'}{flag}"
        )


def cmd_render(args) -> None:
    from videomaker.render import render_job
    from videomaker.spec import load_job

    d = _job_dir(args.name)
    job = d / "job.yaml"
    if not job.exists():
        sys.exit(f"沒有 {job},先跑 parse")
    spec = load_job(job)
    problems = spec.validate()
    if problems:
        sys.exit("job.yaml 有問題:\n" + "\n".join(f"  - {p}" for p in problems))
    final = render_job(d, spec, force=args.force, fonts_dir=FONTS, preview=args.preview)
    print(f"\n成品:{d / final}")


def cmd_export_fcpxml(args) -> None:
    from videomaker.fcpxml import export_fcpxml
    from videomaker.spec import load_job

    d = _job_dir(args.name)
    spec = load_job(d / "job.yaml")
    out = export_fcpxml(d, spec, d / "output" / f"{args.name}.fcpxml")
    print(f"已匯出:{out}(FCP 開啟後全選 Cmd+T 補轉場;字卡/字幕請在 FCP 內加)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="videomaker", description="Lumion 走察影片自動化後製")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("new", help="建立案件資料夾")
    sp.add_argument("name")
    sp.set_defaults(func=cmd_new)

    sp = sub.add_parser("parse", help="業主 brief.txt → job.yaml")
    sp.add_argument("name")
    sp.add_argument("--force", action="store_true", help="覆蓋既有 job.yaml")
    sp.set_defaults(func=cmd_parse)

    sp = sub.add_parser("probe", help="盤點素材規格")
    sp.add_argument("name")
    sp.set_defaults(func=cmd_probe)

    sp = sub.add_parser("render", help="出片")
    sp.add_argument("name")
    sp.add_argument("--force", action="store_true", help="忽略中間檔全部重做")
    sp.add_argument("--preview", action="store_true", help="出 480p 預覽版(output/preview.mp4)")
    sp.set_defaults(func=cmd_render)

    sp = sub.add_parser("export-fcpxml", help="匯出 Final Cut Pro 時間軸草稿")
    sp.add_argument("name")
    sp.set_defaults(func=cmd_export_fcpxml)
    return p


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
