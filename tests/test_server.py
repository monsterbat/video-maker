"""Studio API 測試(用 _demo 案件當 fixture,不動真案件)。

`jobs/_demo` 是**全虛構**的示範案(素材由 `tools/make_demo.py` 合成),
隨 repo 走 —— 所以任何人 clone 下來 `make check` 就該是綠的。
壞掉先跑 `uv run python tools/make_demo.py --force` 重建。
"""

from fastapi.testclient import TestClient

import server

client = TestClient(server.app)


def test_list_jobs_contains_demo():
    r = client.get("/api/jobs")
    assert r.status_code == 200
    names = [j["name"] for j in r.json()]
    assert "_demo" in names


def test_get_job_detail():
    r = client.get("/api/jobs/_demo")
    assert r.status_code == 200
    data = r.json()
    assert data["spec"]["project"] == "範例縣立圖書館新建工程"
    assert len(data["spec"]["clips"]) == 13
    assert len(data["clips_probe"]) == 13


def test_put_spec_roundtrip():
    before = client.get("/api/jobs/_demo").json()["spec"]
    r = client.put("/api/jobs/_demo", json=before)
    assert r.status_code == 200
    after = client.get("/api/jobs/_demo").json()["spec"]
    assert after == before


def test_put_invalid_spec_rejected():
    spec = client.get("/api/jobs/_demo").json()["spec"]
    spec["clips"][0]["caption"]["position"] = "外太空"
    r = client.put("/api/jobs/_demo", json=spec)
    assert r.status_code == 400


def test_unknown_job_404():
    assert client.get("/api/jobs/不存在的案子").status_code == 404


def test_index_serves_ui():
    r = client.get("/")
    assert r.status_code == 200
    assert "VideoMaker Studio" in r.text


def test_overlay_endpoint_returns_png():
    spec = client.get("/api/jobs/_demo").json()["spec"]
    r = client.post("/api/jobs/_demo/overlay", json={"kind": "clip", "index": 1, "spec": spec})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:4] == b"\x89PNG"

    r = client.post(
        "/api/jobs/_demo/overlay",
        json={"kind": "card", "group": "intro", "gindex": 0, "spec": spec},
    )
    assert r.status_code == 200
    assert r.content[:4] == b"\x89PNG"


def test_compose_endpoint_returns_composited_image():
    """靜態排版合成:背景+文字在伺服器端合成單張圖(排版永不跑位的那條路)。"""
    spec = client.get("/api/jobs/_demo").json()["spec"]
    r = client.post("/api/jobs/_demo/compose", json={"kind": "clip", "index": 1, "spec": spec})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"

    r = client.post(
        "/api/jobs/_demo/compose",
        json={"kind": "card", "group": "intro", "gindex": 0, "spec": spec},
    )
    assert r.status_code == 200


def test_render_status_idle():
    r = client.get("/api/jobs/_demo/render/status")
    assert r.status_code == 200
    assert r.json()["running"] is False
