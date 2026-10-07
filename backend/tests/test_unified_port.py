"""Unified single-port serving.

One FastAPI process owns the public port: the built React application is served from `/` (with an
SPA fallback for deep links) and every backend route stays under `/api`. That is what lets a single
tunnel expose the whole application.
"""
import pytest

from app.core.config import settings

BUILD_AVAILABLE = settings.frontend_build_available
requires_build = pytest.mark.skipif(
    not BUILD_AVAILABLE,
    reason="frontend/dist is not built; run `npm run build` in frontend/ to exercise unified serving",
)


def test_api_health_alias_and_versioned_health_share_the_port(client):
    alias = client.get("/api/health")
    assert alias.status_code == 200
    assert alias.json()["status"] == "ok"

    live = client.get("/api/v1/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "alive"

    # API responses must never be cached by a browser or a tunnel.
    assert live.headers["Cache-Control"] == "no-store"


@requires_build
def test_root_serves_the_built_react_application(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="root"' in response.text
    assert response.headers["Cache-Control"] == "no-store"


@requires_build
def test_spa_deep_links_fall_back_to_index_html(client):
    for path in ("/login", "/admin/people", "/student/attendance", "/privacy"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["content-type"].startswith("text/html"), path
        assert 'id="root"' in response.text, path


@requires_build
def test_hashed_assets_are_served_with_immutable_caching(client):
    assets = sorted((settings.frontend_dist_path / "assets").glob("*.js"))
    assert assets, "the Vite build produced no JavaScript assets"
    response = client.get(f"/assets/{assets[0].name}")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"


def test_unknown_api_route_returns_json_not_the_spa(client):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"] in {"API route not found", "Not Found"}


def test_docs_aliases_redirect_to_the_versioned_documentation(client):
    alias = client.get("/docs", follow_redirects=False)
    assert alias.status_code in {307, 308}
    assert alias.headers["location"] in {"/api/v1/docs", "http://testserver/api/v1/docs"}

    document = client.get("/docs")
    assert document.status_code == 200
    assert "swagger" in document.text.lower()

    spec = client.get("/api/v1/openapi.json")
    assert spec.status_code == 200
    assert spec.json()["info"]["title"].startswith("SSAMS")

def test_frame_guard_is_production_only(client, monkeypatch):
    """Local/preview development must stay embeddable; production must refuse framing."""
    assert "X-Frame-Options" not in client.get("/api/health").headers
    monkeypatch.setattr(settings, "app_env", "production")
    assert client.get("/api/health").headers["X-Frame-Options"] == "DENY"
