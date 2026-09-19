#!/usr/bin/env python3
"""把 HTML 打包成「單一檔案」——圖片內嵌成 base64,寄給別人不會破圖。

用法:
    uv run python tools/inline_assets.py docs/工作流總覽.html
    uv run python tools/inline_assets.py docs/*.html -o ~/Desktop/送出

產出 `<原名>_單檔版.html`;沒有外部相依,雙擊即開(手機/Windows/Mac 皆可)。
"""

from __future__ import annotations

import argparse
import base64
import mimetypes
import re
import sys
from pathlib import Path

# src="..." / href="..." / CSS url(...)
PATTERNS = [
    re.compile(r'(?P<pre>(?:src|href)\s*=\s*")(?P<url>[^"]+)(?P<post>")'),
    re.compile(r'(?P<pre>url\(\s*[\'"]?)(?P<url>[^\'")]+)(?P<post>[\'"]?\s*\))'),
]
SKIP_PREFIX = ("data:", "http://", "https://", "//", "#", "mailto:", "javascript:")
INLINE_SUFFIX = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
                 ".woff", ".woff2", ".ttf", ".otf", ".css"}


def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def packed_name(html_path: Path) -> str:
    return f"{html_path.stem}_單檔版.html"


def inline(html_path: Path, out_dir: Path | None = None,
           link_map: dict[Path, str] | None = None) -> Path:
    """link_map:同批打包的 HTML {原始路徑: 新檔名},讓彼此的連結不會斷。"""
    html = html_path.read_text(encoding="utf-8")
    base = html_path.parent
    link_map = link_map or {}
    embedded: list[str] = []
    relinked: list[str] = []
    missing: list[str] = []

    def repl(m: re.Match[str]) -> str:
        url = m.group("url").strip()
        if url.startswith(SKIP_PREFIX):
            return m.group(0)
        target = (base / url.split("?")[0].split("#")[0]).resolve()
        if target in link_map:  # 指向同批的另一份 → 改指打包後的檔名
            relinked.append(f"{url} → {link_map[target]}")
            return m.group("pre") + link_map[target] + m.group("post")
        if target.suffix.lower() not in INLINE_SUFFIX:
            return m.group(0)
        if not target.is_file():
            missing.append(url)
            return m.group(0)
        embedded.append(f"{url} ({target.stat().st_size / 1024:.0f} KB)")
        return m.group("pre") + _data_uri(target) + m.group("post")

    for pat in PATTERNS:
        html = pat.sub(repl, html)

    out_dir = out_dir or html_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / packed_name(html_path)
    out.write_text(html, encoding="utf-8")

    print(f"📄 {html_path.name} → {out}")
    for item in embedded:
        print(f"   ✅ 內嵌 {item}")
    if not embedded:
        print("   ℹ️  本來就沒有外部圖片,原樣複製")
    for item in relinked:
        print(f"   🔗 改連結 {item}")
    for item in missing:
        print(f"   ⚠️  找不到檔案,維持原樣(對方會破圖):{item}")
    print(f"   📦 {html_path.stat().st_size / 1024:.0f} KB → {out.stat().st_size / 1024:.0f} KB")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="把 HTML 的圖片內嵌成 base64,產出單一檔案")
    ap.add_argument("html", nargs="+", type=Path, help="要打包的 HTML")
    ap.add_argument("-o", "--out-dir", type=Path, default=None, help="輸出資料夾(預設同原檔)")
    args = ap.parse_args()

    for p in args.html:
        if not p.is_file():
            print(f"❌ 找不到 {p}", file=sys.stderr)
            return 1
    link_map = {p.resolve(): packed_name(p) for p in args.html}
    for p in args.html:
        inline(p, args.out_dir, link_map)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
