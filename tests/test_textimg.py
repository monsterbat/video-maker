"""疊圖產生器的像素真值測試:錨點、邊界、顏色、縮放。"""

from pathlib import Path

import pytest
from PIL import Image

from videomaker.spec import Caption, Card, Style, Watermark
from videomaker.textimg import caption_watermark_overlay, card_overlay, resolve_font

FONTS = Path(__file__).resolve().parent.parent / "fonts"
STYLE = Style()  # margin 60 / zh 56 / en 36 / shadow 1
W, H = 1920, 1080
M = 60
TOL = 14  # 抗鋸齒與 bearing 的容差(px)


def _opaque_rgb(img, threshold=250):
    region = img.crop(img.getbbox())
    return [
        (r, g, b)
        for r, g, b, a in zip(*(region.getchannel(c).tobytes() for c in "RGBA"))
        if a >= threshold
    ]


def _cap(position, color, zh="測試字幕內容", en=""):
    return caption_watermark_overlay(
        W, H, STYLE, Caption(position, color, zh, en), None, FONTS
    )


def test_font_resolves():
    assert resolve_font(FONTS, "NotoSansTC-Regular.otf").exists()
    with pytest.raises(FileNotFoundError, match="字型"):
        resolve_font(FONTS, "不存在的字型.ttf")


def test_bottom_right_anchors_to_corner():
    img = _cap("bottom_right", "white")
    left, _top, right, bottom = img.getbbox()
    assert abs(right - (W - M)) <= TOL, f"右緣 {right} 應貼齊 {W - M}"
    assert abs(bottom - (H - M)) <= TOL, f"下緣 {bottom} 應貼齊 {H - M}"
    assert left > W // 2, "右下字幕不該延伸過畫面中線"


def test_bottom_left_anchors_to_corner():
    img = _cap("bottom_left", "white")
    left, _, _, bottom = img.getbbox()
    assert abs(left - M) <= TOL
    assert abs(bottom - (H - M)) <= TOL


def test_center_is_centered():
    img = _cap("center", "white")
    left, top, right, bottom = img.getbbox()
    assert abs((left + right) / 2 - W / 2) <= TOL
    assert abs((top + bottom) / 2 - H / 2) <= TOL


def test_colors_white_and_black():
    for color, expect in (("white", 255), ("black", 0)):
        pixels = _opaque_rgb(_cap("bottom_left", color))
        assert pixels, "沒畫出任何實心像素"
        avg = sum(sum(p) for p in pixels) / (3 * len(pixels))
        assert abs(avg - expect) < 30, f"{color} 字實際平均亮度 {avg}"


def test_4k_scales_double():
    small = _cap("bottom_left", "white").getbbox()
    big = caption_watermark_overlay(
        3840, 2160, STYLE, Caption("bottom_left", "white", "測試字幕內容"), None, FONTS
    ).getbbox()
    ratio = (big[2] - big[0]) / (small[2] - small[0])
    assert 1.7 < ratio < 2.3, f"4K 字寬比例 {ratio},應約 2 倍"


def test_bilingual_block_taller():
    zh_only = _cap("bottom_left", "white")
    both = _cap("bottom_left", "white", en="English caption below")
    zh_h = zh_only.getbbox()[3] - zh_only.getbbox()[1]
    both_h = both.getbbox()[3] - both.getbbox()[1]
    assert both_h > zh_h * 1.4


def test_watermark_logo_and_text(tmp_path):
    logo_file = tmp_path / "logo.png"
    Image.new("RGBA", (200, 100), (255, 0, 0, 255)).save(logo_file)
    wm = Watermark(logo="x", logo_height=72, text_zh="案名浮水印", text_en="EN name")
    img = caption_watermark_overlay(W, H, STYLE, None, wm, FONTS, logo_file)
    left, top, _, _ = img.getbbox()
    # 浮水印邊距 24(參考片實測,比字幕的 60 緊);光暈會暈開幾 px,容差放寬
    assert abs(left - 24) <= 6 and abs(top - 24) <= 6, "LOGO 應貼在左上 24px 邊距處"
    # 文字要讓過 LOGO(logo 寬 144 + 間隔),在 x>200 一帶有內容
    text_zone = img.crop((200, 24, W, 300))
    assert text_zone.getbbox(), "浮水印文字應畫在 LOGO 右側"


def test_watermark_recolor_black(tmp_path):
    """color=black 時整塊 LOGO 重上色成黑(RGB 換掉、alpha 保留)——亮景浮水印用。"""
    logo_file = tmp_path / "logo.png"
    Image.new("RGBA", (200, 100), (255, 0, 0, 255)).save(logo_file)
    wm = Watermark(logo="x", logo_height=54, color="black")
    img = caption_watermark_overlay(W, H, STYLE, None, wm, FONTS, logo_file)
    pixels = _opaque_rgb(img)
    assert pixels, "沒畫出浮水印"
    avg = sum(sum(p) for p in pixels) / (3 * len(pixels))
    assert avg < 20, f"黑色浮水印平均亮度應趨近 0,實際 {avg}"
    # 高度 = 54(@1080p 不縮放)
    box = img.getbbox()
    assert abs((box[3] - box[1]) - 54) <= 3


def test_card_line_hierarchy():
    """卡片三級字級:第一行中文=標題最大,其餘中文次之,英文行最小(參考片規格)。"""
    card = Card(bg="black", lines=["範例縣立圖書館新建工程", "新建工程委託規劃設計", "Public Library"])
    img = card_overlay(W, H, STYLE, card, FONTS)
    alpha = img.getchannel("A")
    rows = [
        y for y in range(H)
        if alpha.crop((0, y, W, y + 1)).getbbox()
    ]
    bands: list[tuple[int, int]] = []
    for y in rows:
        if bands and y - bands[-1][1] <= 3:
            bands[-1] = (bands[-1][0], y)
        else:
            bands.append((y, y))
    heights = [b - a + 1 for a, b in bands]
    assert len(heights) == 3, f"應有三行,實際 {len(heights)}"
    title, text, en = heights
    assert title > text > en, f"層級應遞減:標題 {title} > 內文 {text} > 英文 {en}"


def test_card_block_gap_before_agency():
    """參考片版式:英文行之後再接中文(機關名)= 新區塊,間隔(72)遠大於一般行距。"""
    card = Card(bg="black", lines=[
        "範例縣立圖書館新建工程", "新建工程委託規劃設計",
        "New Public Library", "範例縣政府", "Fanli County Government",
    ])
    img = card_overlay(W, H, STYLE, card, FONTS)
    alpha = img.getchannel("A")
    rows = [y for y in range(H) if alpha.crop((0, y, W, y + 1)).getbbox()]
    gaps, prev = [], rows[0]
    for y in rows[1:]:
        if y - prev > 3:
            gaps.append(y - prev)
        prev = y
    assert len(gaps) == 4, f"五行應有四個間隔,實際 {len(gaps)}"
    assert gaps[2] == max(gaps) and gaps[2] > 50, f"機關名前應是大區塊間隔,實際 {gaps}"
    assert gaps[2] > gaps[0] * 1.8, f"區塊間隔應遠大於一般行距 {gaps}"


def test_disclaimer_bottom_line():
    """責任聲明:一行小字貼畫面最底,起點在字幕邊距(參考片:小小一塊,zh14/en12)。"""
    from videomaker.spec import Disclaimer

    disc = Disclaimer(text_zh="本影片由事務所製作,內容受著作權保護。", text_en="Produced by the firm.")
    img = caption_watermark_overlay(W, H, STYLE, None, None, FONTS, disclaimer=disc)
    left, top, _right, bottom = img.getbbox()
    assert abs(left - M) <= 6, f"聲明左緣 {left} 應貼齊字幕邊距 {M}"
    assert H - bottom <= 10, f"聲明應貼近畫面底部,下緣 {bottom}"
    assert bottom - top <= 30, f"聲明是小字,總高 {bottom - top} 不該超過 30px"


def test_disclaimer_never_overflows_any_resolution():
    """回歸測試:480p 曾因字級下限被放大而超出右緣。
    用真實長度等級的聲明,三種解析度都不得超出右邊距。"""
    from videomaker.spec import Disclaimer

    disc = Disclaimer(
        text_zh="本影片由○○建築師事務所製作,內容受著作權保護,未經書面同意,"
                "請勿擅自錄製、轉播、分享或從事任何商業或營利行為,以免觸犯相關法律規範,特此聲明。",
        text_en="This video is produced by Example Architects & Associates. "
                "Please do not record, broadcast, or use it for commercial purposes without permission.",
    )
    for w, h in ((854, 480), (1920, 1080), (3840, 2160)):
        img = caption_watermark_overlay(w, h, STYLE, None, None, FONTS, disclaimer=disc)
        box = img.getbbox()
        assert box, f"{w}x{h} 沒畫出聲明"
        margin = round(60 * h / 1080)
        # getbbox() 量到的是**含暈光**的範圍,而暈光半徑是隨解析度縮放的
        # (1080p 約 8px、4K 約 16px)。容差因此也要跟著縮放 ——
        # 寫死 +8 的話,4K 會因為暈光多糊出來的那幾 px 而誤報。
        halo = round(8 * h / 1080)
        assert box[2] <= w - margin + halo, (
            f"{w}x{h} 聲明右緣 {box[2]} 超出邊距 {w - margin}(容暈光 {halo}px)"
        )


def test_shadow_levels_visibly_differ():
    """無/標準/加強的陰影覆蓋面積要遞增,肉眼才分得出來。"""
    def footprint(level):
        img = caption_watermark_overlay(
            W, H, Style(shadow=level), Caption("bottom_left", "white", "陰影測試字樣"), None, FONTS
        )
        return sum(1 for v in img.getchannel("A").tobytes() if v >= 10)

    f0, f1, f2 = footprint(0), footprint(1), footprint(2)
    assert f1 > f0 * 1.3, f"標準陰影 {f1} 應明顯大於無陰影 {f0}"
    assert f2 > f1 * 1.2, f"加強陰影 {f2} 應明顯大於標準 {f1}"


def test_card_image_zoom(tmp_path):
    from PIL import ImageDraw

    from videomaker.textimg import card_image

    src = Image.new("RGBA", (800, 450), (0, 0, 0, 255))
    ImageDraw.Draw(src).rectangle([360, 205, 440, 245], fill=(255, 255, 255, 255))
    p = tmp_path / "card.png"
    src.save(p)

    def content_w(zoom):
        img = card_image(p, 800, 450, zoom).convert("L").point(lambda v: 255 if v > 128 else 0)
        box = img.getbbox()
        return box[2] - box[0]

    ratio = content_w(2.0) / content_w(1.0)
    assert 1.8 < ratio < 2.2, f"zoom 2 內容應約兩倍,實際 {ratio:.2f}"


def test_card_black_bg_white_centered_text():
    card = Card(bg="black", duration=1.5, lines=["第一行", "第二行", "第三行"])
    img = card_overlay(W, H, STYLE, card, FONTS)
    left, top, right, bottom = img.getbbox()
    assert abs((left + right) / 2 - W / 2) <= TOL
    assert abs((top + bottom) / 2 - H / 2) <= TOL
    pixels = _opaque_rgb(img)
    avg = sum(sum(p) for p in pixels) / (3 * len(pixels))
    assert avg > 225, "黑底卡片應配白字"


def test_card_with_logo_layout(tmp_path):
    logo_file = tmp_path / "logo.png"
    Image.new("RGBA", (300, 150), (0, 0, 255, 255)).save(logo_file)
    card = Card(bg="white", duration=2.5, lines=["案名"], logo="x")
    img = card_overlay(W, H, STYLE, card, FONTS, logo_file)
    # LOGO 高 160,中心在 32% 高度 → 頂約 265
    assert abs(img.getbbox()[1] - 265) <= 4
    # 文字在 52% 高度以下
    assert img.crop((0, round(H * 0.52), W, H)).getbbox(), "卡片文字應在中下區"
    pixels = _opaque_rgb(img.crop((0, round(H * 0.52), W, H)))
    avg = sum(sum(p) for p in pixels) / (3 * len(pixels))
    assert avg < 30, "白底卡片應配黑字"


def _logo_file(tmp_path: Path) -> Path:
    """假 LOGO 塊:719x126(=參考片實測尺寸)的不透明白色橫塊。"""
    p = tmp_path / "logo.png"
    Image.new("RGBA", (719, 126), (255, 255, 255, 255)).save(p)
    return p


def _rows_with_pixels(img: Image.Image) -> list[int]:
    alpha = img.getchannel("A")
    return [y for y in range(img.height) if max(alpha.crop((0, y, img.width, y + 1)).tobytes()) > 40]


def test_card_logo_below_text(tmp_path):
    """多單位卡:文字(工程單位)在上、LOGO 塊(設計單位)在下 —— 順序不能顛倒。"""
    logo = _logo_file(tmp_path)
    card = Card(bg="black", lines=["範例營造股份有限公司"], logo="x.png",
                logo_pos="bottom", logo_height=126)
    img = card_overlay(W, H, STYLE, card, FONTS, logo_path=logo)
    # LOGO 是整條 719px 寬的實心塊 → 找「橫向連續最寬」的那些列就是 LOGO
    alpha = img.getchannel("A")
    widths = {y: sum(1 for v in alpha.crop((0, y, W, y + 1)).tobytes() if v > 40)
              for y in _rows_with_pixels(img)}
    logo_rows = [y for y, wd in widths.items() if wd >= 700]
    text_rows = [y for y, wd in widths.items() if 0 < wd < 700]
    assert logo_rows and text_rows
    assert min(logo_rows) > max(text_rows), "LOGO 應該整塊在文字下方"
    # 整組垂直置中:上下留白差距不大
    top_gap, bottom_gap = min(text_rows), H - max(logo_rows)
    assert abs(top_gap - bottom_gap) <= 40, f"上下留白 {top_gap}/{bottom_gap} 應接近置中"


def test_card_logo_above_text_by_default(tmp_path):
    logo = _logo_file(tmp_path)
    card = Card(bg="black", lines=["範例營造股份有限公司"], logo="x.png", logo_height=126)
    img = card_overlay(W, H, STYLE, card, FONTS, logo_path=logo)
    alpha = img.getchannel("A")
    widths = {y: sum(1 for v in alpha.crop((0, y, W, y + 1)).tobytes() if v > 40)
              for y in _rows_with_pixels(img)}
    logo_rows = [y for y, wd in widths.items() if wd >= 700]
    text_rows = [y for y, wd in widths.items() if 0 < wd < 700]
    assert max(logo_rows) < min(text_rows), "預設 LOGO 在文字上方(參考片的單一單位卡)"
