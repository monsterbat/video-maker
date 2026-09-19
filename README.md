# Video Maker

[English](#english) | [繁體中文](#繁體中文)

<a id="english"></a>

## English

Turn a folder of video clips and a short text brief into a finished, ready-to-deliver video.

Title and end cards, crossfade transitions, bilingual (Chinese and English) subtitles,
a watermark, and background music are added automatically.
Editing that used to be done by hand in Premiere or Final Cut is reduced to a single command.

### Features

- **Single source of truth**: every subtitle, duration, font size, and transition lives in one `job.yaml`.
- **Brief parser**: converts a free-text brief into `job.yaml` and lists anything it cannot resolve for a person to confirm, instead of guessing.
- **Footage audit**: `probe` reports the resolution, frame rate, and length of every clip and flags inconsistencies.
- **Fast previews**: a 480p preview renders before the full-resolution output.
- **Incremental rendering**: each segment is cached by a content hash, so only edited segments are rendered again.
- **Studio web UI**: edit subtitle text, position, and color on a timeline, pick the music start point on a waveform, and trim clips in the browser.
- **Final Cut Pro export**: export the timeline as FCPXML to continue editing in Final Cut Pro.

### Requirements

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/) for dependencies and virtual environments
- ffmpeg 8.x, including ffprobe

### Quick start

```bash
uv sync
cp brand.example.yaml brand.yaml    # optional: company name and copyright notice
uv run python tools/doctor.py       # checks the environment and explains how to fix anything missing
uv run python main.py render _demo --preview
```

The last command renders the bundled demo project to `jobs/_demo/output/preview.mp4`.
The demo project is fictional, and all of its footage, music, and logo are synthetic.

### Working on a project

```bash
uv run python main.py new <name>              # create the project folder
# clips go in input/clips/ (file-name order is playback order),
# music in input/audio/, the logo in input/assets/, and the brief in brief.txt (optional)
uv run python main.py parse <name>            # brief.txt -> job.yaml, plus items to confirm
uv run python main.py probe <name>            # check resolution, frame rate, and length of every clip
uv run python main.py render <name> --preview # 480p preview
uv run python main.py render <name>           # full resolution
uv run python main.py export-fcpxml <name>    # Final Cut Pro timeline
```

`examples/example_job.yaml` documents every field of `job.yaml`.

#### Studio

```bash
make studio    # http://127.0.0.1:8020
```

The studio listens on localhost only by default.

### Design decisions

- **Text is drawn with Pillow and overlaid as images** instead of ffmpeg's `drawtext` or `subtitles` filters.
  Many ffmpeg builds ship without libass or FreeType, and those filters fail there.
- **The filter graph is built directly**, without an ffmpeg wrapper library,
  so the exact command sent to ffmpeg is always visible when something goes wrong.
- **Segments are cached by hash.** Only edited segments are re-rendered; a change to the rendering code triggers a full rebuild.
- **Input that cannot be resolved goes to a person.** The brief parser never guesses,
  because a wrong guess would silently carry through to the delivered video.

### Project layout

| Path | Contents |
|---|---|
| `videomaker/` | Core library: job spec, brief parser, text rendering, ffmpeg graph, FCPXML export |
| `main.py` | Command-line interface |
| `server.py`, `static/` | Studio web UI (FastAPI) |
| `tools/` | Environment check, demo generator, delivery file naming, asset helpers |
| `tests/` | Unit tests and an end-to-end render test |
| `jobs/_demo/` | Synthetic demo project |

### Testing

```bash
make check    # ruff + pytest, including an end-to-end render with synthetic footage
```

### License

Copyright (c) 2026 SC Hsiao. All rights reserved. The source code is published for reference;
please contact the author before using it in your own work.
Fonts are distributed under their own licenses; see [fonts/README.md](fonts/README.md).

---

<a id="繁體中文"></a>

## 繁體中文

把一個資料夾的影片素材,加上一段簡短的文字說明,自動產出可以直接交付的完整影片。

片頭卡、片尾卡、交叉淡化轉場、中英雙語字幕、浮水印與背景音樂都會自動加上。
原本要在 Premiere 或 Final Cut 手動完成的剪輯,縮減為一行指令。

### 功能

- **單一設定檔**:字幕、秒數、字級與轉場全部寫在一份 `job.yaml`。
- **文字說明解析**:把自由格式的文字說明轉成 `job.yaml`;無法判讀的內容會列出來交給人確認,不會自行猜測。
- **素材盤點**:`probe` 會列出每段素材的解析度、幀率與長度,並標出不一致的地方。
- **快速預覽**:先輸出 480p 預覽,確認後再輸出完整解析度。
- **增量渲染**:每個段落以內容雜湊快取,只重新渲染有修改的段落。
- **Studio 網頁介面**:在時間軸上編輯字幕文字、位置與顏色,在音樂波形上挑選起點,並修剪片段長度。
- **匯出 Final Cut Pro**:可把時間軸匯出成 FCPXML,在 Final Cut Pro 中繼續剪輯。

### 系統需求

- Python 3.11 以上
- [uv](https://docs.astral.sh/uv/):管理套件與虛擬環境
- ffmpeg 8.x(含 ffprobe)

### 快速開始

```bash
uv sync
cp brand.example.yaml brand.yaml    # 選填:公司名稱與著作權聲明
uv run python tools/doctor.py       # 檢查執行環境,缺少的項目會說明安裝方式
uv run python main.py render _demo --preview
```

最後一行會用內附的示範專案輸出 `jobs/_demo/output/preview.mp4`。
示範專案是虛構的,影片、音樂與標誌全部由程式合成。

### 製作一個專案

```bash
uv run python main.py new <名稱>              # 建立專案資料夾
# 影片放 input/clips/(依檔名排序即播放順序),
# 音樂放 input/audio/,標誌放 input/assets/,文字說明放 brief.txt(選填)
uv run python main.py parse <名稱>            # brief.txt → job.yaml,並列出需要確認的項目
uv run python main.py probe <名稱>            # 檢查每段素材的解析度、幀率與長度
uv run python main.py render <名稱> --preview # 480p 預覽
uv run python main.py render <名稱>           # 完整解析度
uv run python main.py export-fcpxml <名稱>    # 匯出 Final Cut Pro 時間軸
```

`job.yaml` 的所有欄位說明見 `examples/example_job.yaml`。

#### Studio

```bash
make studio    # http://127.0.0.1:8020
```

Studio 預設只接受本機連線。

### 設計考量

- **文字用 Pillow 繪製成圖片再疊加**,不使用 ffmpeg 的 `drawtext` 或 `subtitles` 濾鏡。
  許多 ffmpeg 版本沒有編入 libass 或 FreeType,這兩個濾鏡在那些環境會失敗。
- **直接組出 filter graph**,不透過 ffmpeg 包裝函式庫,出問題時可以看到實際送給 ffmpeg 的完整指令。
- **以雜湊快取段落**:只重新渲染修改過的段落;渲染程式本身有變動時則全部重建。
- **無法判讀的輸入交給人處理**:文字說明解析器不做猜測,因為猜錯的內容會在沒有提示的情況下一路進到成品。

### 專案結構

| 路徑 | 內容 |
|---|---|
| `videomaker/` | 核心程式庫:專案規格、文字說明解析、文字繪製、ffmpeg 流程、FCPXML 匯出 |
| `main.py` | 命令列介面 |
| `server.py`、`static/` | Studio 網頁介面(FastAPI) |
| `tools/` | 環境檢查、示範專案產生器、交付檔名、素材輔助工具 |
| `tests/` | 單元測試與完整渲染的端對端測試 |
| `jobs/_demo/` | 合成素材的示範專案 |

### 測試

```bash
make check    # ruff + pytest,包含以合成素材跑完整渲染的端對端測試
```

### 授權

Copyright (c) 2026 SC Hsiao. All rights reserved. 保留所有權利。原始碼公開供參考,
如需在自己的作品中使用,請先與作者聯繫。
字型依各自的授權散布,見 [fonts/README.md](fonts/README.md)。
