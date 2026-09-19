"""job.yaml 的資料結構與讀寫。schema 權威在此,example 見 examples/example_job.yaml。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

POSITIONS = ("bottom_left", "bottom_right", "center")
COLORS = ("white", "black")
FITS = ("contain", "cover")
LOGO_POS = ("top", "bottom")


@dataclass
class OutputCfg:
    path: str = "output/final.mp4"
    resolution: str = "auto"  # auto 或 "1920x1080"
    fps: str = "auto"  # auto 或 "30"、"30000/1001"
    # 素材比例跟輸出不同時怎麼辦(實際遇過:同一案內 3840x2528 與 3840x2160 混用)
    # contain=留黑邊(素材完整) | cover=裁切填滿(滿版,切掉超出的邊)
    fit: str = "contain"


@dataclass
class Style:
    font: str = "NotoSansTC-Regular.otf"  # fonts/ 內檔名或絕對路徑
    font_en: str | None = None  # 英文字幕用字型;不設 = 跟中文同一套
    # 機位字幕與左上浮水印的字同級(對齊參考片實測;
    # 浮水印 54px 高的 LOGO 塊內,中文 ≈32、英文 ≈16)
    font_size_zh: int = 32  # px,以 1080p 為基準,依實際輸出高度縮放
    font_size_en: int = 16  # 英文是輔助,明顯小於中文
    margin: int = 60
    outline: int = 0
    shadow: int = 1
    # 卡片(片頭/片尾)三級字級:第一行中文=標題、其餘中文行、英文行
    # 依參考片 1080p 實測:37/31/20px 墨高 → 字級 40/34/22
    card_title_size: int = 40
    card_text_size: int = 34
    card_en_size: int = 22
    # 卡片專用字型(中英文都用);不設 = 跟 style.font 同一套。
    # 參考片的卡片是思源黑體粗體 → 預設 NotoSansTC-Bold.otf(隨 repo 進 git)
    card_font: str | None = "NotoSansTC-Bold.otf"


@dataclass
class Transition:
    type: str = "fade"  # fade=交叉淡化 | black=淡出黑再淡入
    duration: float = 1.0


@dataclass
class AudioCfg:
    music: str | None = None
    music_volume: float = 1.0
    music_start: float = 0.0  # 音樂從第幾秒開始取(跳過前奏用)
    fade_out: float = 3.0
    keep_clip_audio: bool = False


@dataclass
class Watermark:
    logo: str | None = None
    logo_height: int = 54  # 參考片實測:LOGO 塊全高 54px @1080p
    color: str | None = None  # None=LOGO 原色;white/black=整塊重上色(alpha 不動)
    text_zh: str = ""
    text_en: str = ""


@dataclass
class Disclaimer:
    """畫面最底部的著作權責任聲明(小字一行,只疊在機位畫面)。"""

    text_zh: str = ""
    text_en: str = ""
    size_zh: int = 14  # 參考片實測 @1080p
    size_en: int = 12


@dataclass
class Card:
    bg: str = "black"
    duration: float = 1.5
    lines: list[str] = field(default_factory=list)
    logo: str | None = None
    # LOGO 塊放文字上方(參考片的單一單位卡)或下方。
    # bottom 是為了「工程單位在上、設計單位(帶 LOGO)在下」這種多單位卡:
    # 業主寫的先後順序就是單位的角色順序,不能為了版面顛倒(2026-08-05 確立)
    logo_pos: str = "top"
    logo_height: int = 160  # LOGO 塊高度,1080p 基準(參考片的字卡 LOGO 塊實測 126)
    image: str | None = None  # 整張現成字卡圖(業主給的成品卡);設了就優先於 lines/logo
    zoom: float = 1.0  # 字卡內容放大倍數(中心裁切;內容太小時調大)


@dataclass
class Caption:
    position: str = "bottom_left"
    color: str = "white"
    text_zh: str = ""
    text_en: str = ""


@dataclass
class Clip:
    file: str = ""
    caption: Caption | None = None
    start: float = 0.0  # 修剪:從素材第幾秒開始用
    end: float | None = None  # 修剪:用到素材第幾秒(None = 到尾)


@dataclass
class JobSpec:
    project: str = ""
    output: OutputCfg = field(default_factory=OutputCfg)
    style: Style = field(default_factory=Style)
    transition: Transition = field(default_factory=Transition)
    audio: AudioCfg = field(default_factory=AudioCfg)
    watermark: Watermark | None = None
    disclaimer: Disclaimer | None = None
    intro: list[Card] = field(default_factory=list)
    outro: list[Card] = field(default_factory=list)
    clips: list[Clip] = field(default_factory=list)

    def validate(self) -> list[str]:
        """回傳問題清單(空 = 通過)。"""
        problems = []
        if not self.clips:
            problems.append("clips 是空的")
        for i, clip in enumerate(self.clips, 1):
            if clip.caption:
                if clip.caption.position not in POSITIONS:
                    problems.append(f"clip {i}: position 不合法 {clip.caption.position!r}")
                if clip.caption.color not in COLORS:
                    problems.append(f"clip {i}: color 不合法 {clip.caption.color!r}")
            if clip.end is not None and clip.end <= clip.start:
                problems.append(f"clip {i}: 修剪終點 {clip.end} 必須大於起點 {clip.start}")
        if self.transition.type not in ("fade", "black"):
            problems.append(f"transition.type 不合法 {self.transition.type!r}")
        if self.output.fit not in FITS:
            problems.append(f"output.fit 不合法 {self.output.fit!r}(只能 {'/'.join(FITS)})")
        for where, cards in (("intro", self.intro), ("outro", self.outro)):
            for i, card in enumerate(cards, 1):
                if card.logo_pos not in LOGO_POS:
                    problems.append(f"{where} 卡{i}: logo_pos 不合法 {card.logo_pos!r}")
        return problems


def _dataclass_from(cls, data: dict):
    """dict → dataclass,忽略未知欄位、缺欄位用預設值。"""
    fields = {f for f in cls.__dataclass_fields__}
    return cls(**{k: v for k, v in data.items() if k in fields})


def spec_from_dict(data: dict) -> JobSpec:
    spec = JobSpec(project=data.get("project", ""))
    if "output" in data:
        spec.output = _dataclass_from(OutputCfg, data["output"])
        spec.output.resolution = str(spec.output.resolution)
        spec.output.fps = str(spec.output.fps)
    if "style" in data:
        spec.style = _dataclass_from(Style, data["style"])
    if "transition" in data:
        spec.transition = _dataclass_from(Transition, data["transition"])
    if "audio" in data:
        spec.audio = _dataclass_from(AudioCfg, data["audio"])
    if data.get("watermark"):
        spec.watermark = _dataclass_from(Watermark, data["watermark"])
    if data.get("disclaimer"):
        spec.disclaimer = _dataclass_from(Disclaimer, data["disclaimer"])
    for key in ("intro", "outro"):
        setattr(spec, key, [_dataclass_from(Card, c) for c in data.get(key, [])])
    for c in data.get("clips", []):
        clip = _dataclass_from(Clip, {k: v for k, v in c.items() if k != "caption"})
        if c.get("caption"):
            clip.caption = _dataclass_from(Caption, c["caption"])
        spec.clips.append(clip)
    return spec


def load_job(path: Path) -> JobSpec:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise TypeError(f"{path} 不是有效的 job.yaml")
    return spec_from_dict(data)


def save_job(spec: JobSpec, path: Path) -> None:
    data = asdict(spec)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
