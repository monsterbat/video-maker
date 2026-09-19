#!/usr/bin/env python3
"""把透明底 LOGO 整塊重上色(只換 RGB、保留 alpha),黑底/白底卡片各用一張。

用法:
    uv run python tools/recolor_logo.py <來源.png> black -o <輸出.png>

為什麼要有這支:渲染時浮水印能靠 `watermark.color` 即時重上色,但**卡片上的
LOGO 不會**(片尾白底卡放白色 LOGO = 看不見)。第一次是臨時腳本處理的,
第二次再用就該工具化(全域 §十四)。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

COLORS = {"black": (0, 0, 0), "white": (255, 255, 255)}


def recolor(src: Path, color: str, out: Path) -> Path:
    logo = Image.open(src).convert("RGBA")
    solid = Image.new("RGBA", logo.size, COLORS[color] + (255,))
    solid.putalpha(logo.getchannel("A"))
    out.parent.mkdir(parents=True, exist_ok=True)
    solid.save(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="透明底 LOGO 重上色")
    ap.add_argument("src", type=Path)
    ap.add_argument("color", choices=sorted(COLORS))
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()
    out = recolor(args.src, args.color, args.out)
    print(f"✅ {args.src.name} → {out}({args.color})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
