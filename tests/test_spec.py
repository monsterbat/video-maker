"""spec 讀寫的回歸測試(重點:dict → dataclass 不掉欄位)。"""

from videomaker.spec import spec_from_dict


def test_clip_trim_survives_roundtrip():
    """2026-07-28 修的 bug:spec_from_dict 曾把 clips 的 start/end 丟掉,
    Studio 存檔會靜默弄丟修剪。"""
    spec = spec_from_dict({
        "clips": [
            {"file": "a.mp4", "start": 2.5, "end": 8.0,
             "caption": {"position": "bottom_left", "color": "white", "text_zh": "字"}},
            {"file": "b.mp4"},
        ],
    })
    assert spec.clips[0].start == 2.5
    assert spec.clips[0].end == 8.0
    assert spec.clips[0].caption.text_zh == "字"
    assert spec.clips[1].start == 0.0 and spec.clips[1].end is None


def test_disclaimer_and_watermark_color_parse():
    spec = spec_from_dict({
        "clips": [{"file": "a.mp4"}],
        "watermark": {"logo": "logo.png", "color": "black"},
        "disclaimer": {"text_zh": "聲明", "text_en": "EN", "size_zh": 14},
    })
    assert spec.watermark.color == "black"
    assert spec.disclaimer.text_zh == "聲明"
    assert spec.disclaimer.size_en == 12  # 預設值

    assert spec_from_dict({"clips": [{"file": "a.mp4"}]}).disclaimer is None


def test_validate_rejects_bad_fit_and_logo_pos():
    from videomaker.spec import Card, Clip, JobSpec

    spec = JobSpec(clips=[Clip(file="a.mp4")])
    spec.output.fit = "拉伸"
    spec.intro = [Card(logo_pos="middle")]
    problems = spec.validate()
    assert any("fit" in p for p in problems)
    assert any("logo_pos" in p for p in problems)


def test_fit_filter_cover_crops_contain_pads():
    from videomaker.ffmpeg import fit_filter

    cover = fit_filter(1920, 1080, "cover")
    assert "increase" in cover and "crop=1920:1080" in cover and "pad" not in cover
    contain = fit_filter(1920, 1080, "contain")
    assert "decrease" in contain and "pad=1920:1080" in contain and "crop" not in contain
