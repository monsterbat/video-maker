"""端到端:假素材(lavfi 合成)跑完整四階段管線,ffprobe 驗成品。"""

import subprocess
from pathlib import Path

import pytest

from videomaker.ffmpeg import video_info
from videomaker.render import render_job
from videomaker.spec import (
    AudioCfg,
    Caption,
    Card,
    Clip,
    JobSpec,
    Transition,
    Watermark,
    load_job,
    save_job,
)


def _lavfi(out: Path, src: str, *extra: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", src, *extra, str(out)],
        check=True,
    )


@pytest.fixture(scope="module")
def job_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("job")
    clips = d / "input/clips"
    audio = d / "input/audio"
    assets = d / "input/assets"
    for sub in (clips, audio, assets):
        sub.mkdir(parents=True)
    for i, color in enumerate(["red", "green", "blue"], start=1):
        _lavfi(
            clips / f"{i:02d}.mp4",
            f"color=c={color}:s=640x360:r=30:d=2",
            "-pix_fmt", "yuv420p",
        )
    _lavfi(audio / "bgm.wav", "sine=frequency=440:duration=3")
    _lavfi(assets / "logo.png", "color=c=yellow:s=200x100:d=0.1", "-frames:v", "1")
    return d


def _make_spec() -> JobSpec:
    spec = JobSpec(project="測試案")
    spec.transition = Transition(type="fade", duration=0.5)
    spec.audio = AudioCfg(music="input/audio/bgm.wav", fade_out=1.0)
    spec.watermark = Watermark(
        logo="input/assets/logo.png", text_zh="測試案", text_en="Test Project"
    )
    spec.intro = [
        Card(bg="black", duration=1.0, lines=["測試案", "副標", "機關"]),
        Card(bg="black", duration=1.0, image="input/assets/logo.png"),  # 整張字卡路徑
    ]
    spec.outro = [Card(bg="white", duration=1.0, lines=["測試案"])]
    spec.clips = [
        Clip("input/clips/01.mp4", Caption("bottom_left", "white", "左下白字", "EN one")),
        Clip("input/clips/02.mp4", Caption("bottom_right", "black", "右下黑字")),
        Clip("input/clips/03.mp4", Caption("center", "white", "置中白字")),
    ]
    return spec


def test_full_pipeline(job_dir):
    spec = _make_spec()
    save_job(spec, job_dir / "job.yaml")
    spec = load_job(job_dir / "job.yaml")  # 順便驗 YAML round-trip
    assert not spec.validate()

    final = render_job(job_dir, spec)
    out = job_dir / final
    assert out.exists()

    info = video_info(out)
    assert (info.width, info.height) == (640, 360)
    assert info.has_audio, "成品沒有音軌"
    # 6 段共 9s − 5 個轉場 × 0.5s = 6.5s
    assert abs(info.duration - 6.5) < 0.6, f"長度 {info.duration} 偏離預期 6.5s"

    # 中間檔都在(可斷點續跑的基礎)
    work = job_dir / "output/work"
    assert (work / "seg_01.mp4").exists()
    assert (work / "card_in_0.mp4").exists()
    assert (work / "timeline.mp4").exists()


def test_rerun_skips_fresh_segments(job_dir, capsys):
    spec = load_job(job_dir / "job.yaml")
    render_job(job_dir, spec)
    assert "跳過" in capsys.readouterr().out


def test_cache_invalidates_only_changed_seg(job_dir):
    """改機位2的字幕 → 只有 seg_02 重編碼,seg_01 不動。"""
    spec = load_job(job_dir / "job.yaml")
    render_job(job_dir, spec)
    work = job_dir / "output/work"
    m1 = (work / "seg_01.mp4").stat().st_mtime_ns
    m2 = (work / "seg_02.mp4").stat().st_mtime_ns

    spec.clips[1].caption.text_zh = "改過的字幕"
    render_job(job_dir, spec)
    assert (work / "seg_01.mp4").stat().st_mtime_ns == m1, "沒動到的段不該重編碼"
    assert (work / "seg_02.mp4").stat().st_mtime_ns > m2, "動到的段要重編碼"


def test_clip_trim(job_dir):
    spec = load_job(job_dir / "job.yaml")
    spec.clips[0].start = 0.5
    spec.clips[0].end = 1.5
    render_job(job_dir, spec)
    from videomaker.ffmpeg import video_info as vi

    dur = vi(job_dir / "output/work/seg_01.mp4").duration
    assert abs(dur - 1.0) < 0.15, f"修剪後應約 1 秒,實際 {dur}"


def test_music_only_change_skips_stage_c(job_dir):
    """只改音樂設定 → 畫面串接(Stage C)跳過,只重貼音軌(秒級)。"""
    spec = load_job(job_dir / "job.yaml")
    render_job(job_dir, spec)
    timeline = job_dir / "output/work/timeline.mp4"
    t1 = timeline.stat().st_mtime_ns
    final = job_dir / "output/final.mp4"
    f1 = final.stat().st_mtime_ns

    spec.audio.music_volume = 0.5
    spec.audio.music_start = 1.0
    render_job(job_dir, spec)
    assert timeline.stat().st_mtime_ns == t1, "音樂改動不該重做畫面串接"
    assert final.stat().st_mtime_ns > f1, "成品要重新 mux"


def test_preview_render(job_dir):
    spec = load_job(job_dir / "job.yaml")
    out = render_job(job_dir, spec, preview=True)
    p = job_dir / out
    # 輸出版本化:實體檔帶時間戳,固定名是指向最新版的 symlink
    assert p.name.startswith("preview_") and p.exists()
    latest = job_dir / "output/preview.mp4"
    assert latest.is_symlink() and latest.resolve() == p.resolve()
    assert video_info(p).height <= 480
    # 預覽用獨立 work 目錄,不弄髒正式中間檔
    assert (job_dir / "output/work_preview").is_dir()


def test_versioned_output_keeps_old_file(job_dir):
    """固定名底下若是版本化之前的實體舊檔,要改名保留、不可覆蓋。"""
    old = job_dir / "output/final.mp4"
    if old.is_symlink():
        old.unlink()
    old.write_bytes(b"legacy")
    spec = load_job(job_dir / "job.yaml")
    render_job(job_dir, spec, force=True)
    kept = [p for p in (job_dir / "output").glob("final_*.mp4") if p.read_bytes()[:6] == b"legacy"]
    assert kept, "舊實體檔應被改名保留"
    assert (job_dir / "output/final.mp4").is_symlink()


def test_snap_fps():
    from videomaker.render import _snap_fps

    assert _snap_fps("5000000/83333") == "60"  # Lumion 4K60 輸出的非標準幀率
    assert _snap_fps("30000/1001") == "30000/1001"
    assert _snap_fps("30/1") == "30"
    assert _snap_fps("12") == "12"  # 非常見幀率保持原樣


def test_transition_longer_than_segment_fails_clearly(job_dir):
    spec = load_job(job_dir / "job.yaml")
    spec.transition.duration = 1.5  # 卡片只有 1.0s
    with pytest.raises(Exception, match="轉場"):
        render_job(job_dir, spec, force=True)
