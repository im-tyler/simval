import shutil
import zipfile
from pathlib import Path

from simval.omex import export_omex
from simval.oracle import get_case
from simval.pipeline import diagnose

WAVE = Path(__file__).parent.parent / "examples" / "wave" / "pulse"


def test_export_omex_creates_archive(tmp_path):
    run = tmp_path / "w"
    run.mkdir()
    shutil.copy(WAVE / "wave.json", run / "wave.json")
    diagnose(run, selection="n/a")  # writes provenance.json
    out = tmp_path / "run.omex"
    info = export_omex(run, out)
    assert info["entries"][0] == "manifest.xml"
    assert "provenance.json" in info["entries"]
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert "manifest.xml" in names
        assert "omexManifest" in z.read("manifest.xml").decode()


def test_case_info_returns_provenance():
    case = get_case("kepler_two_body")
    assert case.engine == "nbody-rebound"
    assert "energy_relative_range" in case.reference_metrics
    assert case.source  # documented provenance
