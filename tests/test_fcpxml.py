"""FCPXML 匯出:結構合法、機位齊、音樂在 lane -1。"""

import xml.etree.ElementTree as ET
from pathlib import Path

from videomaker.fcpxml import export_fcpxml
from videomaker.spec import load_job

DEMO = Path(__file__).resolve().parent.parent / "jobs" / "_demo"


def test_export_demo(tmp_path):
    spec = load_job(DEMO / "job.yaml")
    out = export_fcpxml(DEMO, spec, tmp_path / "demo.fcpxml")
    text = out.read_text(encoding="utf-8")
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>')

    root = ET.fromstring(text.split("\n", 2)[2])
    spine = root.find(".//spine")
    top_clips = spine.findall("asset-clip")
    assert len(top_clips) == 13, "13 個機位都要上時間軸"
    music = spine.find("asset-clip/asset-clip[@lane='-1']")
    assert music is not None, "音樂要掛在 lane -1"
    # 時間都要對齊幀界(有理數格式)
    for c in top_clips:
        assert c.get("duration").endswith("s") and "/" in c.get("duration")
