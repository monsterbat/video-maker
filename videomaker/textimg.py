"""文字/LOGO 疊圖產生(Pillow)。

為什麼不用 libass/drawtext:homebrew ffmpeg 8.x 精簡版沒編 libass/freetype,
subtitles/drawtext 濾鏡不存在(2026-07-27 實測)。改在 Python 端把整張畫面的
文字+LOGO 畫成透明 PNG,ffmpeg 只做 overlay——像素級定位、任何 TTF/OTF 丟
fonts/ 就能用、不依賴 ffmpeg 編譯選項。

座標紀律:右下角字幕以「右下錨點向左延伸」計算(固定需求),所有邊距以
1080p 為基準等比縮放。
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .spec import Caption, Card, Disclaimer, Style, Watermark

_COLORS = {"white": (255, 255, 255, 255), "black": (0, 0, 0, 255)}
_SHADOW_BASE = {"white": (0, 0, 0), "black": (255, 255, 255)}  # 對比色:白字黑暈、黑字白暈

Line = tuple[str, ImageFont.FreeTypeFont]


def _has_cjk(text: str) -> bool:
    """卡片行的層級判定:含中日韓字 = 中文行,否則當英文行(小字)。"""
    return any(
        0x4E00 <= ord(ch) <= 0x9FFF or 0x3400 <= ord(ch) <= 0x4DBF or 0xF900 <= ord(ch) <= 0xFAFF
        for ch in text
    )


def resolve_font(fonts_dir: Path | None, name: str) -> Path:
    """style.font 可以是 fonts/ 內的檔名,或字型檔絕對路徑。"""
    p = Path(name)
    if p.is_absolute() and p.exists():
        return p
    if fonts_dir and (fonts_dir / name).exists():
        return fonts_dir / name
    raise FileNotFoundError(
        f"找不到字型「{name}」;把字型檔放進 fonts/ 或在 job.yaml 的 style.font 填絕對路徑"
    )


def _measure(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int, int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top, left, top


def _draw_block(
    img: Image.Image,
    lines: list[Line],
    color: str,
    *,
    anchor: str,  # bottom_left | bottom_right | center | top_left | top_center
    margin: int,
    gap: int | list[int],  # 單一值 = 每行等距;list = 逐行間距(len(lines)-1 個)
    origin: tuple[int, int] | None = None,  # top_* 錨點的起點
    shadow_level: int = 0,  # 0 無 / 1 標準 / 2 加強
    scale: float = 1.0,
) -> None:
    """把多行(可各自字級)文字當一個區塊,依錨點畫上 img。"""
    draw = ImageDraw.Draw(img)
    w, h = img.size
    sizes = [_measure(draw, text, font) for text, font in lines]
    gaps = gap if isinstance(gap, list) else [gap] * (len(lines) - 1)
    total_h = sum(s[1] for s in sizes) + sum(gaps)

    if anchor in ("bottom_left", "bottom_right"):
        y = h - margin - total_h
    elif anchor == "center":
        y = (h - total_h) // 2
    else:  # top_left / top_center
        y = origin[1] if origin else margin

    placed: list[tuple[tuple[int, int], str, ImageFont.FreeTypeFont]] = []
    for i, ((text, font), (tw, th, ox, oy)) in enumerate(zip(lines, sizes)):
        if anchor in ("bottom_left", "top_left"):
            x = origin[0] if (origin and anchor == "top_left") else margin
        elif anchor == "bottom_right":
            x = w - margin - tw
        else:  # center / top_center
            x = (w - tw) // 2
        # textbbox 的 bearing 補償,讓視覺邊界剛好落在計算位置
        placed.append(((x - ox, y - oy), text, font))
        y += th + (gaps[i] if i < len(gaps) else 0)

    if shadow_level > 0:
        img.alpha_composite(_halo(img.size, placed, color, shadow_level, scale))
    for pos, text, font in placed:
        draw.text(pos, text, font=font, fill=_COLORS[color])


def _halo(size, placed, color: str, level: int, scale: float) -> Image.Image:
    """模糊光暈陰影(仿 Premiere drop shadow)。等級差要肉眼可辨:
    標準 = 小位移+窄暈;加強 = 大位移+寬暈+疊兩層。"""
    alpha = 175 if level == 1 else 255
    off = round((2 + level) * scale)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    fill = _SHADOW_BASE[color] + (alpha,)
    for pos, text, font in placed:
        d.text((pos[0] + off, pos[1] + off), text, font=font, fill=fill)
    layer = layer.filter(ImageFilter.GaussianBlur(radius=(1 + 2 * level) * scale))
    if level >= 2:
        layer = Image.alpha_composite(layer, layer)
    return layer


def card_image(path: Path, w: int, h: int, zoom: float = 1.0) -> Image.Image:
    """業主給的整張成品字卡:縮放鋪滿輸出解析度。zoom > 1 = 中心裁切放大內容。"""
    img = Image.open(path).convert("RGBA")
    if zoom and zoom > 1:
        cw, ch = round(img.width / zoom), round(img.height / zoom)
        left, top = (img.width - cw) // 2, (img.height - ch) // 2
        img = img.crop((left, top, left + cw, top + ch))
    return img.resize((w, h), Image.LANCZOS)


def card_frame(
    w: int,
    h: int,
    style: Style,
    card: Card,
    fonts_dir: Path | None,
    logo_path: Path | None = None,
    image_path: Path | None = None,
) -> Image.Image:
    """完整卡片畫面(含底色),給即時預覽用。"""
    if image_path:
        return card_image(image_path, w, h, card.zoom)
    bg = (255, 255, 255, 255) if card.bg == "white" else (0, 0, 0, 255)
    base = Image.new("RGBA", (w, h), bg)
    base.alpha_composite(card_overlay(w, h, style, card, fonts_dir, logo_path))
    return base


def _paste_logo(
    img: Image.Image,
    logo_path: Path,
    height: int,
    pos: tuple[int, int],
    color: str | None = None,
) -> int:
    """回傳縮放後的 LOGO 寬度。透明邊自動裁掉再縮放;color 設 white/black 時
    整塊重上色(只換 RGB、保留 alpha)——同一張 LOGO 檔黑白場景都能用。"""
    logo = Image.open(logo_path).convert("RGBA")
    bbox = logo.getbbox()
    if bbox:
        logo = logo.crop(bbox)
    if color in _COLORS:
        solid = Image.new("RGBA", logo.size, _COLORS[color])
        solid.putalpha(logo.getchannel("A"))
        logo = solid
    width = round(logo.width * height / logo.height)
    logo = logo.resize((width, height), Image.LANCZOS)
    img.alpha_composite(logo, pos)
    return width


def caption_watermark_overlay(
    w: int,
    h: int,
    style: Style,
    caption: Caption | None,
    watermark: Watermark | None,
    fonts_dir: Path | None,
    logo_path: Path | None = None,
    disclaimer: Disclaimer | None = None,
) -> Image.Image:
    """單一機位的整張覆蓋層:角落字幕 + 左上浮水印(LOGO+文字)+ 底部責任聲明。"""
    scale = h / 1080
    m = round(style.margin * scale)
    gap = round(10 * scale)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    font_zh = ImageFont.truetype(
        str(resolve_font(fonts_dir, style.font)), round(style.font_size_zh * scale)
    )
    font_en = ImageFont.truetype(
        str(resolve_font(fonts_dir, style.font_en or style.font)),
        round(style.font_size_en * scale),
    )

    if caption and caption.text_zh:
        lines: list[Line] = [(caption.text_zh, font_zh)]
        if caption.text_en:
            lines.append((caption.text_en, font_en))
        _draw_block(
            img, lines, caption.color,
            anchor=caption.position, margin=m, gap=gap,
            shadow_level=style.shadow, scale=scale,
        )

    if watermark:
        # 浮水印的邊距比字幕緊(參考片實測 24px,不是 60px)
        wm_m = round(24 * scale)
        text_x = wm_m
        if logo_path:
            logo_h = round(watermark.logo_height * scale)
            logo_w = _paste_logo(img, logo_path, logo_h, (wm_m, wm_m), watermark.color)
            text_x = wm_m + logo_w + round(16 * scale)
        if watermark.text_zh:
            wm_lines: list[Line] = [(watermark.text_zh, font_en)]  # 浮水印用小字
            if watermark.text_en:
                wm_lines.append((watermark.text_en, font_en))
            _draw_block(
                img, wm_lines, watermark.color or "white",
                anchor="top_left", margin=wm_m, gap=round(4 * scale), origin=(text_x, wm_m),
                shadow_level=style.shadow, scale=scale,
            )

    if disclaimer and disclaimer.text_zh:
        _draw_disclaimer(img, disclaimer, style, fonts_dir, m, scale)
    return img


def _draw_disclaimer(
    img: Image.Image,
    disc: Disclaimer,
    style: Style,
    fonts_dir: Path | None,
    margin_x: int,
    scale: float,
) -> None:
    """底部一行小字聲明:中文在前、英文接在後(同一行、各自字級),白字＋淡黑暈。
    參考片實測:字級 zh14/en12,底邊距 ~8px @1080p。
    ⚠️ 不設字級下限——預覽必須是成品的等比縮小版(2026-07-28 曾因 8px 下限
    讓 480p 聲明爆出右緣);太長時整行等比縮到塞進左右邊距。"""
    draw = ImageDraw.Draw(img)
    zh_file = str(resolve_font(fonts_dir, style.font))
    en_file = str(resolve_font(fonts_dir, style.font_en or style.font))
    gap = round(24 * scale)

    def _fonts(k: float):
        # 縮小時無條件捨去——round 會把小幅縮減圓回原字級,等於沒縮
        f_zh = ImageFont.truetype(zh_file, max(int(disc.size_zh * scale * k), 4))
        f_en = ImageFont.truetype(en_file, max(int(disc.size_en * scale * k), 4))
        return f_zh, f_en

    def _total(f_zh, f_en) -> int:
        zh = _measure(draw, disc.text_zh, f_zh)[0]
        en = _measure(draw, disc.text_en, f_en)[0] if disc.text_en else 0
        return zh + (gap + en if disc.text_en else 0)

    k = 1.0
    f_zh, f_en = _fonts(k)
    avail = img.width - 2 * margin_x
    for _ in range(3):  # 迭代收斂(字級取整會讓一次縮不到位)
        total = _total(f_zh, f_en)
        if total <= avail or avail <= 0 or k <= 0.3:
            break
        k *= avail / total * 0.98
        f_zh, f_en = _fonts(k)

    zh_w, zh_h, zh_ox, zh_oy = _measure(draw, disc.text_zh, f_zh)
    y_base = img.height - round(8 * scale)  # 文字下緣
    placed: list[tuple[tuple[int, int], str, ImageFont.FreeTypeFont]] = [
        ((margin_x - zh_ox, y_base - zh_h - zh_oy), disc.text_zh, f_zh)
    ]
    if disc.text_en:
        _en_w, en_h, en_ox, en_oy = _measure(draw, disc.text_en, f_en)
        placed.append(
            ((margin_x + zh_w + gap - en_ox, y_base - en_h - en_oy),
             disc.text_en, f_en)
        )
    img.alpha_composite(_halo(img.size, placed, "white", 1, scale))
    for pos, text, font in placed:
        draw.text(pos, text, font=font, fill=_COLORS["white"])


def _block_height(img: Image.Image, lines: list[Line], gaps: list[int]) -> int:
    """多行文字當一個區塊時的總高(排 LOGO 位置要先知道文字佔多高)。"""
    draw = ImageDraw.Draw(img)
    return sum(_measure(draw, text, font)[1] for text, font in lines) + sum(gaps)


def _card_gaps(texts: list[str], scale: float) -> list[int]:
    """卡片逐行間距(參考片實測 @1080p):中→中 28、中→英 20、英→英 8;
    英→中 72 = 區塊分隔(標題區塊 與 機關名區塊 之間的大空隙)。"""
    gaps = []
    for prev, nxt in pairwise(texts):
        p, n = _has_cjk(prev), _has_cjk(nxt)
        if p and n:
            g = 28
        elif p and not n:
            g = 20
        elif not p and not n:
            g = 8
        else:  # 英文行之後又出現中文行 → 新區塊
            g = 72
        gaps.append(round(g * scale))
    return gaps


def card_overlay(
    w: int,
    h: int,
    style: Style,
    card: Card,
    fonts_dir: Path | None,
    logo_path: Path | None = None,
) -> Image.Image:
    """片頭/片尾卡覆蓋層:置中文字;有 LOGO 時 LOGO 在上、文字在中下。

    字級層級(參考片規格):第一行中文=標題最大,其餘中文行次之,英文行最小。
    """
    scale = h / 1080
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    color = "black" if card.bg == "white" else "white"
    # 卡片有專用字型(card_font,預設思源黑體粗體=參考片);中英文同一套
    font_file = str(resolve_font(fonts_dir, style.card_font or style.font))
    f_title = ImageFont.truetype(font_file, round(style.card_title_size * scale))
    f_text = ImageFont.truetype(font_file, round(style.card_text_size * scale))
    f_en = ImageFont.truetype(font_file, round(style.card_en_size * scale))
    lines: list[Line] = []
    seen_zh = False
    for line in card.lines:
        if _has_cjk(line):
            lines.append((line, f_text if seen_zh else f_title))
            seen_zh = True
        else:
            lines.append((line, f_en))
    gaps = _card_gaps([t for t, _ in lines], scale)

    if logo_path:
        logo_h = round(card.logo_height * scale)
        logo = Image.open(logo_path).convert("RGBA")
        if bbox := logo.getbbox():  # 透明邊裁掉,不然「高度」量到的是空白
            logo = logo.crop(bbox)
        logo_w = round(logo.width * logo_h / logo.height)
        logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
        m = round(style.margin * scale)
        if card.logo_pos == "bottom":
            # 文字在上、LOGO 塊在下,整組垂直置中(多單位卡:工程單位在前、設計單位在後)
            block_gap = round(72 * scale)  # 與 _card_gaps 的「區塊分隔」同一個數字
            text_h = _block_height(img, lines, gaps) if lines else 0
            total = text_h + block_gap + logo_h if lines else logo_h
            y0 = (h - total) // 2
            if lines:
                _draw_block(
                    img, lines, color,
                    anchor="top_center", margin=m, gap=gaps, origin=(0, y0),
                )
            img.alpha_composite(
                logo, ((w - logo_w) // 2, y0 + (text_h + block_gap if lines else 0))
            )
        else:
            img.alpha_composite(logo, ((w - logo_w) // 2, round(h * 0.32 - logo_h / 2)))
            if lines:
                _draw_block(
                    img, lines, color,
                    anchor="top_center", margin=m, gap=gaps, origin=(0, round(h * 0.52)),
                )
    elif lines:
        _draw_block(
            img, lines, color,
            anchor="center", margin=round(style.margin * scale), gap=gaps,
        )
    return img
