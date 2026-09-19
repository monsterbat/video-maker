"""業主文字 brief → JobSpec。

規則式解析:解不了的行收進 warnings 退人工,絕不捏造內容(全域 §十四)。
格式說明見 docs/brief格式.md,可跑的實例見 jobs/_demo/brief.txt。
"""

from __future__ import annotations

import re
from pathlib import Path

from .spec import Caption, Card, Clip, JobSpec, Watermark

_POSITION_MAP = {
    "左下": "bottom_left",
    "右下": "bottom_right",
    "中間": "center",
    "中央": "center",
    "置中": "center",
}
_COLOR_MAP = {"白": "white", "黑": "black"}

# 機位1文字:左下白字(校園入口至活動中心模擬圖)+下方英文字
# 也容忍「左下中文(...)」這種沒寫顏色的變體
# 注意:字幕內容用**貪婪** `(.+)`:業主的字幕常自己帶括號(例:
#    「器材庫房正面(甲棟)整體模擬圖」),非貪婪會在第一個 `)` 就斷掉、
#    默默吞掉後半段字幕。貪婪 = 吃到該行最後一個 `)`。
_RE_CLIP = re.compile(
    r"機位(\d+)\s*文字?\s*:\s*(左下|右下|中間|中央|置中|左上|右上)?"
    r"(?:(白|黑)字|中文)?\s*\((.+)\)\s*(\+?\s*下方英文字)?"
)
# 片頭黑幕1開始(1.5秒) / 片頭黑幕2 (2~3秒):... / 結尾白幕1開始(1.5秒)
_RE_CARD = re.compile(
    r"(片頭|開頭|片尾|結尾)(黑|白)幕(\d+)[^\d(]*\(\s*([\d.]+)\s*(?:~\s*([\d.]+))?\s*秒\s*\)"
)
# 「開始片頭顯示三行文字」之類的指示行(卡片內容的前導,跳過)
_RE_CARD_HINT = re.compile(r"顯示.*文字")
# 每個機位左上角放片頭2(中文+英文+LOGO)
_RE_WATERMARK = re.compile(r"每個機位.*(左上|右上|左下|右下).*片頭(\d+)?")
# 卡片內容行尾的「給我們的指示」括號,不是要顯示的字:
#   範例營造股份有限公司(工程單位)(中文+英文)
#   範例建築師事務所(設計單位)(中文+英文+LOGO)
# 只認帶這些關鍵字的括號 —— 業主真正要顯示的括號(例:
# 「興建工程委託規劃設計(暨後續擴充履約監造)」)不含關鍵字,不會被誤剝。
_RE_CARD_META = re.compile(r"\(([^()]*(?:中文|英文|LOGO|logo|單位)[^()]*)\)")

_VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}


def _natural_key(name: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name)]


# 全形 → 半形(用 unicode escape 寫死,避免編輯器/寫檔把全形字元弄丟)
_FULLWIDTH = {
    "：": ":",  # ：
    "（": "(",  # （
    "）": ")",  # ）
    "＋": "+",  # ＋
    "～": "~",  # ～
    "〜": "~",  # 〜(wave dash)
}


def _normalize(text: str) -> str:
    for full, half in _FULLWIDTH.items():
        text = text.replace(full, half)
    return text


def _split_card_meta(line: str) -> tuple[str, list[str]]:
    """卡片內容行 → (要顯示的字, 業主給我們的指示們)。"""
    metas = _RE_CARD_META.findall(line)
    return _RE_CARD_META.sub("", line).strip(), metas


def parse_brief(text: str, job_dir: Path | None = None) -> tuple[JobSpec, list[str]]:
    """解析業主 brief。回傳 (spec, warnings)。"""
    spec = JobSpec()
    warnings: list[str] = []
    lines = _normalize(text).splitlines()

    captions: dict[int, Caption] = {}
    en_pending: list[int] = []  # 有「下方英文字」但沒給內文的機位
    pending_card: Card | None = None  # 正在收集內容行的卡片
    wm_card_idx: int | None = None  # 浮水印指名要放哪張片頭卡的內容
    card_en_pending: list[str] = []  # 卡片行標了「中文+英文」但沒給英文的
    card_logo_owner: list[str] = []  # 卡片行標了 LOGO 的單位
    card_meta_dropped: list[str] = []  # 被剝掉的指示,列給人看免得以為漏字

    for raw in lines:
        line = raw.strip()
        if not line:
            pending_card = None
            continue

        m = _RE_CLIP.search(line)
        if m:
            pending_card = None
            n = int(m.group(1))
            pos_zh, color_zh, text_zh, has_en = m.group(2), m.group(3), m.group(4), m.group(5)
            position = _POSITION_MAP.get(pos_zh or "")
            if position is None:
                warnings.append(f"機位{n}:位置「{pos_zh}」看不懂,先用左下,請人工確認")
                position = "bottom_left"
            color = _COLOR_MAP.get(color_zh or "")
            if color is None:
                warnings.append(f"機位{n}:沒指定黑/白字,先用白字,請人工確認")
                color = "white"
            captions[n] = Caption(position=position, color=color, text_zh=text_zh)
            if has_en:
                en_pending.append(n)
            continue

        m = _RE_CARD.search(line)
        if m:
            head, bg_zh, _idx, d1, d2 = m.groups()
            duration = (float(d1) + float(d2)) / 2 if d2 else float(d1)
            card = Card(bg="black" if bg_zh == "黑" else "white", duration=duration)
            # 卡片行本身若帶內容描述「:文字(中文+英文+LOGO)」→ 內容沒給,標記待補
            tail = line[m.end() :]
            if "LOGO" in tail.upper():
                card.logo = "input/assets/logo.png"
                warnings.append(
                    f"{head}{bg_zh}幕{_idx}:業主只寫「{tail.lstrip(':')}」沒給實際內文,"
                    "請在 job.yaml 補 lines(LOGO 檔請放 input/assets/logo.png)"
                )
            target = spec.intro if head in ("片頭", "開頭") else spec.outro
            target.append(card)
            # 標題行後只剩標點(「片頭黑幕2 (2~3秒):」)= 內容在下面幾行,繼續收
            rest = tail.strip().lstrip(":").strip()
            pending_card = card if not rest or _RE_CARD_HINT.search(rest) else None
            continue

        if _RE_CARD_HINT.fullmatch(line) or _RE_CARD_HINT.search(line) and len(line) < 15:
            continue  # 「開始片頭顯示三行文字」指示行

        m = _RE_WATERMARK.search(line)
        if m:
            pending_card = None
            spec.watermark = Watermark(logo="input/assets/logo.png")
            if m.group(1) != "左上":
                warnings.append(f"浮水印位置「{m.group(1)}」目前只支援左上,請人工確認")
            if m.group(2):
                wm_card_idx = int(m.group(2))
            continue

        if pending_card is not None:
            text, metas = _split_card_meta(line)
            pending_card.lines.append(text)
            for meta in metas:
                if "LOGO" in meta.upper():
                    pending_card.logo = "input/assets/logo.png"
                    card_logo_owner.append(text)
                if "英文" in meta:
                    card_en_pending.append(text)
                card_meta_dropped.append(f"{text}({meta})")
            continue

        warnings.append(f"看不懂的行(已忽略):{line}")

    # 專案名 = 片頭卡1 第一行
    if spec.intro and spec.intro[0].lines:
        spec.project = spec.intro[0].lines[0]

    # 浮水印文字:業主寫「每個機位左上角放片頭N」→ 就拿那張卡的內容
    if spec.watermark is not None:
        src = (
            spec.intro[wm_card_idx - 1]
            if wm_card_idx and 1 <= wm_card_idx <= len(spec.intro)
            else None
        )
        if src is not None and len(src.lines) > 1:
            warnings.append(
                f"浮水印要放片頭卡{wm_card_idx}的內容,但那張卡有 {len(src.lines)} 行"
                f"({'、'.join(src.lines)})——浮水印只放得下一組中英文,"
                "請人工決定要放哪個單位(或做一張含兩個單位的浮水印圖)"
            )
        else:
            spec.watermark.text_zh = src.lines[0] if src and src.lines else spec.project
            warnings.append("浮水印英文(text_en)業主沒給內文,請在 job.yaml 補")

    # LOGO 卡片的 lines 沒內容 → 先放專案名
    for card in spec.intro + spec.outro:
        if card.logo and not card.lines and spec.project:
            card.lines = [spec.project]

    if en_pending:
        warnings.append(
            f"機位 {','.join(map(str, en_pending))} 要「下方英文字」但業主沒給英文內文,"
            "請在 job.yaml 各 clip 補 text_en(或叫 AI 翻譯後人工確認)"
        )
    if card_meta_dropped:
        warnings.append(
            "卡片行的括號註記已當成「給製作端的指示」剝掉、不會顯示在畫面上:"
            + "、".join(dict.fromkeys(card_meta_dropped))
        )
    if card_en_pending:
        warnings.append(
            f"卡片行 {'、'.join(dict.fromkeys(card_en_pending))} 業主要中英文但沒給英文,"
            "請在 job.yaml 該卡片 lines 補英文行(不捏造)"
        )
    if card_logo_owner:
        warnings.append(
            f"卡片 LOGO 是 {'、'.join(dict.fromkeys(card_logo_owner))} 的;"
            "目前卡片 LOGO 一律置中畫在文字上方(一張卡只放得下一個),"
            "多單位卡請確認版面(LOGO 檔放 input/assets/logo.png)"
        )

    # 機位 → 檔案配對
    files = _find_clip_files(job_dir) if job_dir else []
    nums = sorted(captions)
    if nums != list(range(1, len(nums) + 1)):
        warnings.append(f"機位編號不連續:{nums}")
    for i, n in enumerate(nums):
        if i < len(files):
            file = files[i]
        else:
            file = f"input/clips/{n:02d}.mp4"
        spec.clips.append(Clip(file=file, caption=captions[n]))
    if files and len(files) != len(nums):
        warnings.append(
            f"機位 {len(nums)} 個但 input/clips/ 有 {len(files)} 支影片,請人工確認配對"
        )

    return spec, warnings


def _find_clip_files(job_dir: Path) -> list[str]:
    clips_dir = job_dir / "input" / "clips"
    if not clips_dir.is_dir():
        return []
    files = [
        p for p in clips_dir.iterdir() if p.suffix.lower() in _VIDEO_EXTS and not p.name.startswith(".")
    ]
    files.sort(key=lambda p: _natural_key(p.name))
    return [str(p.relative_to(job_dir)) for p in files]
