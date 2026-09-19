"""四階段渲染管線(見 DESIGN.md §三):

A. 逐 clip 正規化 + 疊字幕/浮水印 PNG → output/work/seg_NN.mp4
B. 片頭/片尾卡(色底 + 文字 LOGO PNG)→ output/work/card_*.mp4
C. xfade 交叉淡化串接                 → output/work/timeline.mp4
D. 配樂 + 淡出 mux                    → output/final.mp4

中間檔已存在且比來源新就跳過(--force 全部重做),一段壞了只重跑一段。
所有 ffmpeg 都以 job_dir 為 cwd;文字一律 Pillow 畫成 PNG 再 overlay(見 textimg.py)。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from . import ffmpeg, textimg
from .ffmpeg import FfmpegError
from .spec import Card, Clip, JobSpec


@dataclass
class Segment:
    path: Path  # 相對 job_dir
    duration: float


# Lumion 等軟體會寫出怪異幀率(如 5000000/83333 ≈ 60.0002),吸附到最近的常見幀率,
# 避免奇怪的 timebase 讓 xfade 拒收、播放器顯示 60.0002fps
_COMMON_FPS = [
    (23.976, "24000/1001"), (24.0, "24"), (25.0, "25"), (29.97, "30000/1001"),
    (30.0, "30"), (50.0, "50"), (59.94, "60000/1001"), (60.0, "60"),
]


def _snap_fps(fps: str) -> str:
    try:
        num, _, den = fps.partition("/")
        value = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return fps
    rate, text = min(_COMMON_FPS, key=lambda item: abs(value - item[0]))
    return text if abs(value - rate) < 0.02 else fps




class Renderer:
    def __init__(
        self,
        job_dir: Path,
        spec: JobSpec,
        force: bool = False,
        fonts_dir: Path | None = None,
        preview: bool = False,
    ):
        self.job_dir = job_dir
        self.spec = spec
        self.force = force
        self.preview = preview
        # 預設用專案根目錄的 fonts/(思源黑體隨 repo 走)
        self.fonts_dir = fonts_dir or Path(__file__).resolve().parent.parent / "fonts"
        # preview 用獨立 work 目錄,不弄髒 4K 中間檔快取
        self.work = Path("output/work_preview" if preview else "output/work")
        (job_dir / self.work).mkdir(parents=True, exist_ok=True)
        self.job_yaml = job_dir / "job.yaml"
        self.w, self.h, self.fps = self._resolve_format()
        if preview and self.h > 480:
            self.w = round(self.w * 480 / self.h / 2) * 2
            self.h = 480
        # 輸出版本化(新輸出不覆蓋舊檔):實體檔帶時間戳,
        # 固定名(preview.mp4 / final.mp4)只是指向最新版的 symlink
        base = Path("output/preview.mp4") if preview else Path(spec.output.path)
        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        self.latest_rel = base
        self.out_rel = base.with_name(f"{base.stem}_{stamp}{base.suffix}")
        self.encoder = ffmpeg.pick_encoder()

    # ---------- 格式決定 ----------

    def _resolve_format(self) -> tuple[int, int, str]:
        out = self.spec.output
        if out.resolution != "auto" and out.fps != "auto":
            w, h = out.resolution.lower().split("x")
            return int(w), int(h), out.fps
        if not self.spec.clips:
            raise FfmpegError("沒有任何 clip,無法決定輸出格式")
        first = ffmpeg.video_info(self.job_dir / self.spec.clips[0].file)
        if out.resolution == "auto":
            w, h = first.width, first.height
        else:
            ws, hs = out.resolution.lower().split("x")
            w, h = int(ws), int(hs)
        fps = first.fps if out.fps == "auto" else out.fps
        return w, h, _snap_fps(fps)

    # ---------- 共用 ----------

    def _encode_args(self) -> list[str]:
        if self.encoder == "h264_videotoolbox":
            # 位元率按解析度給:4K 給太低會糊、480p 給太高浪費
            pixels = self.w * self.h
            rate = "3M" if pixels <= 854 * 480 else ("12M" if pixels <= 1920 * 1080 else "35M")
            return ["-c:v", self.encoder, "-b:v", rate, "-pix_fmt", "yuv420p", "-an"]
        return ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-an"]

    def _run(self, args: list[str]) -> None:
        ffmpeg.run(["ffmpeg", "-y", "-v", "error", *args], cwd=self.job_dir)

    def _cached(self, out: Path, payload: dict, files: list[Path]) -> bool:
        """每段獨立快取:只比對「影響這一段」的設定+來源檔。改一個字幕只重做那一段。"""
        tag = self.job_dir / out.with_suffix(".hash")
        h = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode())
        h.update(f"{self.w}x{self.h}@{self.fps}".encode())
        # 管線程式碼本身也是快取鍵:渲染邏輯改了(如陰影演算法)舊段必須失效
        for f in sorted(Path(__file__).resolve().parent.glob("*.py")):
            h.update(f"{f.name}:{f.stat().st_mtime_ns}".encode())
        for f in files:
            st = f.stat()
            h.update(f"{f.name}:{st.st_size}:{st.st_mtime_ns}".encode())
        digest = h.hexdigest()
        hit = (
            not self.force
            and (self.job_dir / out).exists()
            and tag.exists()
            and tag.read_text() == digest
        )
        if not hit:
            tag.write_text(digest)  # 渲染失敗時 out 不存在,下次不會誤判命中
        return hit

    def _existing(self, rel: str | None, what: str) -> Path | None:
        """相對路徑檔案存在 → 絕對路徑;不存在 → 警告 + None(先出無該素材版本)。"""
        if not rel:
            return None
        p = self.job_dir / rel
        if p.exists():
            return p
        print(f"  ⚠️ {what}不存在({rel}),先跳過該素材出片")
        return None

    # ---------- Stage B:卡片 ----------

    def _render_card(self, card: Card, name: str) -> Segment:
        out = self.work / f"{name}.mp4"
        png = self.work / f"{name}.png"
        image = self._existing(card.image, f"{name} 的字卡圖")
        logo = None if image else self._existing(card.logo, f"{name} 的 LOGO")

        if image:
            # 業主給的整張成品字卡:縮放鋪滿當整段畫面
            overlay = textimg.card_image(image, self.w, self.h, card.zoom)
        else:
            overlay = textimg.card_overlay(
                self.w, self.h, self.spec.style, card, self.fonts_dir, logo
            )
        overlay.save(self.job_dir / png)

        payload = {"card": asdict(card), "style": asdict(self.spec.style)}
        if self._cached(out, payload, [p for p in (image, logo) if p]):
            print(f"  ⏭  {name} 沒變,跳過")
        else:
            self._run([
                "-f", "lavfi",
                "-i", f"color=c={card.bg}:s={self.w}x{self.h}:d={card.duration}:r={self.fps}",
                "-i", str(png),
                "-filter_complex", "[0:v][1:v]overlay=0:0,setsar=1",
                *self._encode_args(), str(out),
            ])
            print(f"  ✅ {name}({card.duration}s {card.bg})")
        return Segment(out, ffmpeg.video_info(self.job_dir / out).duration)

    # ---------- Stage A:機位 ----------

    def _render_clip(self, clip: Clip, idx: int) -> Segment:
        out = self.work / f"seg_{idx:02d}.mp4"
        png = self.work / f"seg_{idx:02d}.png"
        src = self.job_dir / clip.file
        if not src.exists():
            raise FfmpegError(f"機位 {idx} 的影片不存在:{clip.file}")

        wm = self.spec.watermark
        disc = self.spec.disclaimer
        logo = self._existing(wm.logo, "浮水印 LOGO") if wm else None
        overlay = textimg.caption_watermark_overlay(
            self.w, self.h, self.spec.style, clip.caption, wm, self.fonts_dir, logo,
            disclaimer=disc,
        )
        overlay.save(self.job_dir / png)

        payload = {
            "clip": asdict(clip),
            "style": asdict(self.spec.style),
            "watermark": asdict(wm) if wm else None,
            "disclaimer": asdict(disc) if disc else None,
            "fit": self.spec.output.fit,
        }
        if self._cached(out, payload, [src] + ([logo] if logo else [])):
            print(f"  ⏭  seg_{idx:02d} 沒變,跳過")
        else:
            chain = (
                f"[0:v]{ffmpeg.fit_filter(self.w, self.h, self.spec.output.fit)},"
                f"fps={self.fps},setsar=1[v0];[v0][1:v]overlay=0:0"
            )
            args = []
            if clip.start:
                args += ["-ss", f"{clip.start:.3f}"]  # 放在 -i 前:快速定位,重編碼下仍幀準
            args += ["-i", clip.file, "-i", str(png), "-filter_complex", chain]
            if clip.end is not None:
                args += ["-t", f"{clip.end - clip.start:.3f}"]
            self._run([*args, *self._encode_args(), str(out)])
            trim = f"(修剪 {clip.start}–{clip.end or '尾'})" if clip.start or clip.end else ""
            print(f"  ✅ seg_{idx:02d} ← {clip.file}{trim}")
        return Segment(out, ffmpeg.video_info(self.job_dir / out).duration)

    # ---------- Stage C:串接 ----------

    def _concat(self, segments: list[Segment]) -> Path:
        out = self.work / "timeline.mp4"
        trans = self.spec.transition
        xfade = {"fade": "fade", "black": "fadeblack"}[trans.type]
        d = trans.duration

        for seg in segments:
            if seg.duration <= d:
                raise FfmpegError(
                    f"{seg.path} 長度 {seg.duration:.2f}s ≤ 轉場 {d}s,無法交叉淡化;"
                    "請縮短 transition.duration 或加長該段"
                )

        # 畫面段全沒變 + 轉場設定沒變 → 跳過整條串接(音樂類改動就只剩重貼音軌,秒級)
        payload = {
            "transition": {"type": trans.type, "duration": trans.duration},
            "segs": [[str(s.path), round(s.duration, 3)] for s in segments],
        }
        if self._cached(out, payload, [self.job_dir / s.path for s in segments]):
            print("  ⏭  畫面沒變,跳過串接")
            return out

        if len(segments) == 1:
            self._run(["-i", str(segments[0].path), "-c", "copy", str(out)])
            return out

        args: list[str] = []
        for seg in segments:
            args += ["-i", str(seg.path)]
        # xfade 要求所有輸入 timebase 一致,先各自 settb 統一
        chains = [f"[{i}:v]settb=AVTB[t{i}]" for i in range(len(segments))]
        offset = 0.0
        prev = "[t0]"
        for i, seg in enumerate(segments[1:], start=1):
            offset += segments[i - 1].duration - d
            label = f"[x{i}]" if i < len(segments) - 1 else "[vout]"
            chains.append(
                f"{prev}[t{i}]xfade=transition={xfade}:duration={d}:offset={offset:.3f}{label}"
            )
            prev = label
        args += ["-filter_complex", ";".join(chains), "-map", "[vout]", *self._encode_args(), str(out)]
        self._run(args)
        return out

    # ---------- Stage D:音訊 ----------

    def _mux_audio(self, timeline: Path) -> Path:
        final_rel = self.out_rel
        (self.job_dir / final_rel).parent.mkdir(parents=True, exist_ok=True)
        cfg = self.spec.audio
        total = ffmpeg.video_info(self.job_dir / timeline).duration

        music = self._existing(cfg.music, "音樂檔")
        if not music:
            self._run(["-i", str(timeline), "-c", "copy", str(final_rel)])
            return final_rel

        fade = min(cfg.fade_out, total)
        s = cfg.music_start
        af = (
            f"[1:a]atrim={s:.3f}:{s + total:.3f},asetpts=PTS-STARTPTS,"
            f"volume={cfg.music_volume},"
            f"afade=t=out:st={max(total - fade, 0):.3f}:d={fade:.3f}[aout]"
        )
        self._run([
            "-i", str(timeline),
            "-stream_loop", "-1", "-i", str(music.relative_to(self.job_dir)),
            "-filter_complex", af,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", f"{total:.3f}", str(final_rel),
        ])
        return final_rel

    def _link_latest(self, target_rel: Path) -> None:
        """固定名(preview.mp4/final.mp4)= 指向最新版的 symlink。
        碰到版本化之前留下的實體檔:用它自己的修改時間改名保留,絕不覆蓋。"""
        link = self.job_dir / self.latest_rel
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            old = (
                datetime.fromtimestamp(link.stat().st_mtime).astimezone()
                .strftime("%Y%m%d-%H%M%S")
            )
            dest = link.with_name(f"{link.stem}_{old}{link.suffix}")
            if dest.exists():
                dest = link.with_name(f"{link.stem}_{old}_舊{link.suffix}")
            link.rename(dest)
            print(f"  📦 舊版保留為 {dest.name}")
        link.symlink_to(os.path.relpath(self.job_dir / target_rel, link.parent))

    # ---------- 主流程 ----------

    def render(self) -> Path:
        spec = self.spec
        if spec.audio.keep_clip_audio:
            print("  ⚠️ keep_clip_audio 尚未支援,clip 原聲已忽略(見 TODO)")
        print(f"輸出格式:{self.w}x{self.h} @ {self.fps} fps,編碼 {self.encoder}")

        segments: list[Segment] = []
        print("Stage B|片頭卡")
        for i, card in enumerate(spec.intro):
            segments.append(self._render_card(card, f"card_in_{i}"))
        print("Stage A|機位")
        for i, clip in enumerate(spec.clips, start=1):
            segments.append(self._render_clip(clip, i))
        print("Stage B|片尾卡")
        segments += [self._render_card(c, f"card_out_{i}") for i, c in enumerate(spec.outro)]

        print("Stage C|轉場串接")
        timeline = self._concat(segments)
        print("Stage D|配樂")
        final = self._mux_audio(timeline)
        self._link_latest(final)

        expect = sum(s.duration for s in segments) - spec.transition.duration * (len(segments) - 1)
        actual = ffmpeg.video_info(self.job_dir / final).duration
        print(f"完成:{final}(預期 {expect:.1f}s / 實際 {actual:.1f}s;{self.latest_rel.name} → 最新版)")
        if abs(expect - actual) > 1.0:
            print("  ⚠️ 長度落差 > 1 秒,請人工檢查")
        return final


def render_job(
    job_dir: Path,
    spec: JobSpec,
    force: bool = False,
    fonts_dir: Path | None = None,
    preview: bool = False,
) -> Path:
    return Renderer(job_dir, spec, force=force, fonts_dir=fonts_dir, preview=preview).render()
