# Fonts

[English](#english) | [繁體中文](#繁體中文)

<a id="english"></a>

## English

The project code is copyrighted by its author (see the root `LICENSE`).
Font files are third-party works and are distributed under their own licenses.

Only the fonts named in `job.yaml` (`style.font`, `style.font_en`, `style.card_font`) are used for rendering.

### Bundled fonts

| File | License | Redistribution |
|---|---|---|
| `NotoSansTC-Regular.otf`, `NotoSansTC-Bold.otf` | SIL Open Font License 1.1 | Allowed, including commercial use |

These two files are the defaults, so the demo project renders without any extra downloads.
Additional weights of Noto Sans CJK (also OFL) are available from the
[noto-cjk releases](https://github.com/notofonts/noto-cjk/releases). They are not bundled because the full set is about 142 MB.

### Adding a font

1. Put the font file in `fonts/`.
2. Set its file name in `job.yaml` (`style.font` for subtitles, `style.card_font` for title and end cards).

Check the font's license before committing it. Fonts that may not be redistributed,
such as most commercial fonts and fonts bundled with an operating system, should stay out of the repository.
Missing fonts do not break rendering; the default font is used instead.

---

<a id="繁體中文"></a>

## 繁體中文

專案程式碼的著作權屬於作者(見根目錄的 `LICENSE`);字型檔是第三方作品,依各自的授權散布。

渲染時只會用到 `job.yaml` 裡 `style.font`、`style.font_en`、`style.card_font` 指定的字型。

### 隨專案附上的字型

| 檔案 | 授權 | 可否散布 |
|---|---|---|
| `NotoSansTC-Regular.otf`、`NotoSansTC-Bold.otf` | SIL Open Font License 1.1 | 可以,含商業用途 |

這兩個檔就是預設字型,所以示範專案不必另外下載字型就能出片。
需要 Noto Sans CJK 的其他字重(同樣是 OFL),可從 [noto-cjk releases](https://github.com/notofonts/noto-cjk/releases) 下載;
因為全部字重約 142 MB,沒有隨專案附上。

### 加入新字型

1. 把字型檔放進 `fonts/`。
2. 在 `job.yaml` 填入檔名(字幕用 `style.font`,片頭與片尾卡用 `style.card_font`)。

放進版本紀錄之前,先確認字型的授權允許散布。不能散布的字型(多數商業字型、作業系統內附字型)不要放進專案。
缺少字型不會讓渲染失敗,會改用預設字型。
