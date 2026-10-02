"""`fusion serve` must not be drivable by any other website: loopback bind, Host allowlist (DNS rebinding)
and a per-launch token on every non-GET API call."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fusion_first.web.serve import ServeError, create_local_app, find_dist, serve
from fusion_first.web.settings import Settings

TOKEN = "t0k3n-for-tests-only"
INDEX = "<!doctype html><html><head><title>Fusion</title></head><body><div id=root></div></body></html>"
LOCAL = "http://127.0.0.1:8765"


@pytest.fixture
def dist(tmp_path):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text(INDEX, encoding="utf-8")
    (d / "assets" / "app.js").write_text("console.log('fusion')", encoding="utf-8")
    (d / "logo.png").write_bytes(b"\x89PNG-not-really")
    (tmp_path / "secret.txt").write_text("outside the dist dir", encoding="utf-8")
    return d


@pytest.fixture
def client(dist):
    app = create_local_app(dist, token=TOKEN, settings=Settings(version="test"))
    return TestClient(app, base_url=LOCAL)


# ------------------------------------------------------------------ the page and its token

@pytest.mark.integration
def test_index_carries_the_launch_token(client):
    r = client.get("/")
    assert r.status_code == 200
    assert f'<meta name="fusion-token" content="{TOKEN}">' in r.text
    assert "<div id=root>" in r.text
    assert r.headers["cache-control"] == "no-store"  # a token must not outlive its launch in a cache


@pytest.mark.integration
def test_client_routes_fall_back_to_the_app_page(client):
    r = client.get("/scan")
    assert r.status_code == 200
    assert TOKEN in r.text


@pytest.mark.integration
def test_built_assets_are_served(client):
    assert client.get("/assets/app.js").text == "console.log('fusion')"
    assert client.get("/logo.png").content == b"\x89PNG-not-really"


@pytest.mark.integration
@pytest.mark.parametrize("path", ["/..%2fsecret.txt", "/%2e%2e/secret.txt", "/assets/..%2f..%2fsecret.txt"])
def test_files_outside_the_build_are_never_served(client, path):
    r = client.get(path)
    assert "outside the dist dir" not in r.text


@pytest.mark.integration
def test_absolute_paths_are_never_served(client, dist):
    # On Windows `dist / "C:/.../secret.txt"` is that absolute path: joining alone is not a guard.
    secret = (dist.parent / "secret.txt").resolve().as_posix()
    r = client.get("/" + secret.lstrip("/"))
    assert "outside the dist dir" not in r.text


@pytest.mark.integration
def test_unknown_api_paths_are_404_not_the_app_page(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert TOKEN not in r.text


@pytest.mark.integration
def test_each_launch_gets_a_fresh_token(dist):
    pages = [
        TestClient(create_local_app(dist, settings=Settings(version="test")), base_url=LOCAL).get("/").text
        for _ in range(2)
    ]
    assert pages[0] != pages[1]


# ------------------------------------------------------------------ the token gate

@pytest.mark.integration
def test_api_writes_need_the_token(client):
    body = {"system_prompt": "You are a helpful bot."}
    assert client.post("/api/harden", json=body).status_code == 403
    assert client.post("/api/harden", json=body, headers={"X-Fusion-Token": "wrong"}).status_code == 403
    ok = client.post("/api/harden", json=body, headers={"X-Fusion-Token": TOKEN})
    assert ok.status_code == 200
    assert "hardened_prompt" in ok.json()


@pytest.mark.integration
def test_scans_need_the_token(client):
    body = {"system_prompt": "You are a helpful bot.", "mode": "live", "backend": "ollama"}
    r = client.post("/api/scan/stream", json=body)
    assert r.status_code == 403  # refused before any backend is touched


@pytest.mark.integration
def test_reads_do_not_need_the_token(client):
    assert client.get("/api/health").status_code == 200


@pytest.mark.integration
@pytest.mark.parametrize("path", ["/", "/scan", "/api/health"])
def test_pages_refuse_to_be_framed(client, path):
    # Clickjacking: another site could frame the real, token-bearing page and trick a click.
    r = client.get(path)
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


# ------------------------------------------------------------------ host allowlist, CORS, backends

@pytest.mark.integration
def test_foreign_host_header_is_refused(client):
    # DNS rebinding: evil.example resolves to 127.0.0.1, so the browser sends Host: evil.example.
    r = client.get("/", headers={"host": "evil.example:8765"})
    assert r.status_code == 400
    assert TOKEN not in r.text


@pytest.mark.integration
def test_localhost_name_is_accepted(dist):
    c = TestClient(create_local_app(dist, token=TOKEN, settings=Settings(version="test")),
                   base_url="http://localhost:8765")
    assert c.get("/").status_code == 200


@pytest.mark.integration
def test_no_cross_origin_access(client):
    r = client.get("/api/version", headers={"Origin": "http://localhost:5173"})
    assert "access-control-allow-origin" not in r.headers


@pytest.mark.integration
def test_local_backends_are_on_by_default(client):
    assert client.get("/api/version").json()["backends"]["local_backends_enabled"] is True


@pytest.mark.integration
def test_demo_only_keeps_local_backends_off(dist):
    app = create_local_app(dist, token=TOKEN, settings=Settings(version="test"), local_backends=False)
    c = TestClient(app, base_url=LOCAL)
    assert c.get("/api/version").json()["backends"]["local_backends_enabled"] is False


# ------------------------------------------------------------------ locating the build, launching

@pytest.mark.unit
def test_find_dist_uses_an_explicit_dir(dist):
    assert find_dist(str(dist)) == dist


@pytest.mark.unit
def test_find_dist_refuses_a_dir_without_index(tmp_path):
    with pytest.raises(ServeError, match="index.html"):
        find_dist(str(tmp_path))


@pytest.mark.unit
def test_find_dist_env_override(dist, monkeypatch):
    monkeypatch.setenv("FUSION_WEB_DIST", str(dist))
    assert find_dist(None) == dist


@pytest.mark.unit
@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.20", "::", "example.com"])
def test_serve_refuses_non_loopback_hosts(dist, host):
    with pytest.raises(ServeError, match="127.0.0.1"):
        serve(host=host, dist=str(dist), open_browser=False, run=lambda *a, **k: None)


@pytest.mark.unit
def test_serve_binds_loopback_and_runs(dist):
    calls = []
    serve(host="localhost", port=9911, dist=str(dist), open_browser=False,
          run=lambda app, **kw: calls.append(kw))
    assert calls == [{"host": "127.0.0.1", "port": 9911, "log_level": "warning"}]


@pytest.mark.unit
def test_busy_port_fails_cleanly_before_announcing_or_opening_a_browser(dist, capsys, monkeypatch):
    import socket
    import webbrowser

    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))
    ran = []
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.bind(("127.0.0.1", 0))
        held.listen()
        port = held.getsockname()[1]
        with pytest.raises(ServeError, match="in use"):
            serve(port=port, dist=str(dist), open_browser=True, run=lambda app, **kw: ran.append(kw))
    assert ran == [] and opened == []
    assert "running" not in capsys.readouterr().out


@pytest.mark.unit
def test_a_server_that_cannot_start_is_a_clean_error(dist):
    def fails(app, **kw):
        raise OSError(10048, "address already in use")

    with pytest.raises(ServeError, match="could not start"):
        serve(port=9912, dist=str(dist), open_browser=False, run=fails)


@pytest.mark.unit
def test_cli_serve_reports_a_missing_build(tmp_path, capsys):
    from fusion_first.cli import main

    assert main(["serve", "--dist", str(tmp_path), "--no-open"]) == 2
    assert "npm --prefix frontend run build" in capsys.readouterr().out
