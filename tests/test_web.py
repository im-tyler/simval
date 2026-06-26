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


def test_api_series_and_compare(tmp_path):
    import shutil

    pytest.importorskip("MDAnalysisTests.datafiles", reason="needs datafiles")
    from MDAnalysisTests import datafiles

    run = tmp_path / "adk"
    run.mkdir()
    shutil.copy(datafiles.XTC, run / "traj.xtc")
    shutil.copy(datafiles.GRO, run / "conf.gro")
    client = TestClient(app)
    s = client.get(f"/api/series?run_dir={run}").json()
    assert s["engine"] == "gromacs"
    assert "rmsd_nm" in s["series"]
    c = client.get(f"/api/compare?run_a={run}&run_b={run}").json()
    assert c["run_a"] and c["deltas"] is not None
