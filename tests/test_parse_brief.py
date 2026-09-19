"""解析器測試。

fixture 是**虛構**的業主 brief,但**句型是從真實案子歸納出來的** ——
每一種形態都對應一種實際出現過的寫法,改動時請保留形態、只改內容文字。
(不放真實客戶案名,避免客戶資料進入版本紀錄)
"""

from videomaker.parse_brief import parse_brief

# 形態一:最常見的完整案子 —— 兩張片頭卡、13 個機位、兩張片尾卡、浮水印。
LIBRARY_BRIEF = """\
片頭黑幕1開始(1.5秒)
開始片頭顯示三行文字
範例縣立圖書館新建工程
新建工程委託規劃設計(暨後續擴充履約監造)
範例縣政府

片頭黑幕2 (2~3秒)：文字(中文+英文+LOGO)

每個機位左上角放片頭2(中文+英文+LOGO)
機位1文字：左下白字(校園入口至圖書館模擬圖)+下方英文字
機位2文字：右下白字(圖書館正立面模擬圖)+下方英文字
機位3文字：右下白字(前側遮陽格柵細節模擬圖)+下方英文字
機位4文字：左下中文(入口門廊及停車場模擬圖)+下方英文字
機位5文字：左下白字(側立面及周邊環境模擬圖)+下方英文字
機位6文字：左下黑字(後側庭園模擬圖)+下方英文字
機位7文字：右下黑字(中庭天井採光模擬圖)+下方英文字
機位8文字：右下黑字(圖書館背立面模擬圖)+下方英文字
機位9文字：左下黑字(門廳與閱覽區關係模擬圖)+下方英文字
機位10文字：左下白字(兒童閱覽室整體鳥瞰模擬圖)+下方英文字
機位11文字：右下黑字(階梯閱覽區及書牆模擬圖)+下方英文字
機位12文字：右下黑字(自習室整體模擬圖)+下方英文字
機位13文字：左下白字(屋頂平台至中庭整體關係模擬圖)+下方英文字

結尾白幕1開始(1.5秒)
開始片頭顯示三行文字
範例縣立圖書館新建工程
新建工程委託規劃設計(暨後續擴充履約監造)
範例縣政府
結尾白幕2 (2~3秒)：文字(中文+英文+LOGO)
"""


def test_full_parse():
    spec, warnings = parse_brief(LIBRARY_BRIEF)

    assert spec.project == "範例縣立圖書館新建工程"
    assert len(spec.clips) == 13

    c1 = spec.clips[0].caption
    assert (c1.position, c1.color, c1.text_zh) == (
        "bottom_left", "white", "校園入口至圖書館模擬圖"
    )
    c2 = spec.clips[1].caption
    assert (c2.position, c2.color) == ("bottom_right", "white")
    # 機位4「左下中文」沒寫顏色 → 預設白 + 警告
    assert spec.clips[3].caption.color == "white"
    assert any("機位4" in w for w in warnings)
    c6 = spec.clips[5].caption
    assert (c6.position, c6.color, c6.text_zh) == ("bottom_left", "black", "後側庭園模擬圖")
    c11 = spec.clips[10].caption
    assert (c11.position, c11.color) == ("bottom_right", "black")
    c13 = spec.clips[12].caption
    assert (c13.position, c13.color, c13.text_zh) == (
        "bottom_left", "white", "屋頂平台至中庭整體關係模擬圖"
    )

    # 片頭:黑幕1(1.5s 三行)+ 黑幕2(2~3 秒取 2.5,LOGO)
    assert len(spec.intro) == 2
    assert spec.intro[0].bg == "black"
    assert spec.intro[0].duration == 1.5
    assert spec.intro[0].lines == [
        "範例縣立圖書館新建工程",
        "新建工程委託規劃設計(暨後續擴充履約監造)",
        "範例縣政府",
    ]
    assert spec.intro[1].duration == 2.5
    assert spec.intro[1].logo

    # 片尾:白幕 ×2
    assert len(spec.outro) == 2
    assert spec.outro[0].bg == "white"
    assert spec.outro[0].lines[0] == "範例縣立圖書館新建工程"
    assert spec.outro[1].bg == "white"

    # 浮水印(每機位左上角)
    assert spec.watermark is not None
    assert spec.watermark.text_zh == "範例縣立圖書館新建工程"

    # 英文業主沒給 → 警告,不捏造
    assert all(c.caption.text_en == "" for c in spec.clips)
    assert any("英文" in w for w in warnings)

    # 預設檔名對應
    assert spec.clips[0].file == "input/clips/01.mp4"
    assert spec.clips[12].file == "input/clips/13.mp4"


def test_clip_files_matched_from_dir(tmp_path):
    (tmp_path / "input/clips").mkdir(parents=True)
    # 亂序建檔,驗證自然排序配對
    for name in ["機位10.mp4", "機位2.mp4", "機位1.mp4"]:
        (tmp_path / "input/clips" / name).touch()
    brief = (
        "機位1文字:左下白字(甲)\n機位2文字:右下黑字(乙)\n機位3文字:左下白字(丙)\n"
    )
    spec, _warnings = parse_brief(brief, job_dir=tmp_path)
    assert [c.file for c in spec.clips] == [
        "input/clips/機位1.mp4", "input/clips/機位2.mp4", "input/clips/機位10.mp4"
    ]


def test_garbage_line_goes_to_warnings():
    _spec, warnings = parse_brief("機位1文字:左下白字(甲)\n這行是火星文完全無法解析\n")
    assert any("火星文" in w for w in warnings)


# 形態二(三種特殊寫法):
#   ① 字幕內容自己帶括號  ② 卡片內容寫在標題行的下一行  ③ 一張卡兩個單位
NESTED_BRIEF = """\
片頭黑幕1開始(1.5秒)
開始片頭顯示三行文字
範例園區
場館整修統包工程
範例主管機關

片頭黑幕2 (2~3秒)：
顯示二行文字
範例營造股份有限公司(工程單位)(中文+英文)
範例建築師事務所(設計單位)(中文+英文+LOGO)

每個機位左上角放片頭2(中文+英文+LOGO)  大小要注意一下
機位1文字：左下黑字(器材庫房正面(甲棟)整體模擬圖)+下方英文字
機位2文字：右下白字(training庫房(乙棟及丙棟)外觀修繕模擬圖)+下方英文字
"""


def test_caption_keeps_nested_parentheses():
    """業主字幕自己帶括號時不准被截斷(非貪婪會斷在第一個右括號)。"""
    spec, _warnings = parse_brief(NESTED_BRIEF)
    assert spec.clips[0].caption.text_zh == "器材庫房正面(甲棟)整體模擬圖"
    assert spec.clips[1].caption.text_zh == "training庫房(乙棟及丙棟)外觀修繕模擬圖"
    assert spec.clips[0].caption.color == "black"
    assert spec.clips[1].caption.position == "bottom_right"


def test_card_content_on_following_lines():
    """「片頭黑幕2 (2~3秒):」後面沒接內容 → 下面幾行才是卡片內容。"""
    spec, warnings = parse_brief(NESTED_BRIEF)
    card2 = spec.intro[1]
    assert card2.duration == 2.5
    # 括號註記是給製作端的指示,不顯示在畫面上
    assert card2.lines == ["範例營造股份有限公司", "範例建築師事務所"]
    assert card2.logo  # (中文+英文+LOGO) → 這張卡要放 LOGO
    assert any("範例營造股份有限公司" in w and "英文" in w for w in warnings)
    assert any("範例建築師事務所" in w and "LOGO" in w for w in warnings)
    # 剝掉的註記要講出來,免得以為漏字
    assert any("工程單位" in w for w in warnings)


def test_watermark_from_multi_unit_card_is_not_guessed():
    """浮水印指名放片頭2,但那張卡有兩個單位 → 退人工,不亂挑一個。"""
    spec, warnings = parse_brief(NESTED_BRIEF)
    assert spec.watermark is not None
    assert spec.watermark.text_zh == ""
    assert any(
        "浮水印" in w and "片頭卡2" in w and "範例營造股份有限公司" in w for w in warnings
    )
