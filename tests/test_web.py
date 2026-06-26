import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from simval.web import app


def test_dashboard_serves():
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "simval" in r.text


def test_api_engines_and_cases():
    client = TestClient(app)
    engines = client.get("/api/engines").json()["engines"]
    assert "gromacs" in engines
    cases = client.get("/api/cases").json()["cases"]
    assert "adk_morph" in cases
