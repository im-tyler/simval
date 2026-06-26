import shutil
from pathlib import Path

import pytest

pytest.importorskip("MDAnalysis")
datafiles = pytest.importorskip("MDAnalysisTests.datafiles")

from simval import service
from simval.context import EngineAdapter, GromacsEngine, RunContext, SyntheticEngine, _ENGINES, register_engine, select_engine
from simval.fixtures import make_run_dir


def test_select_synthetic_engine(tmp_path):
    run = make_run_dir(tmp_path / "s", good=True)
    assert isinstance(select_engine(run), SyntheticEngine)


def test_select_gromacs_engine(tmp_path):
    run = tmp_path / "g"
    run.mkdir()
    shutil.copy(datafiles.XTC, run / "traj.xtc")
    shutil.copy(datafiles.GRO, run / "conf.gro")
    assert isinstance(select_engine(run), GromacsEngine)


def test_inspect_snapshot(tmp_path):
    run = make_run_dir(tmp_path / "s2", good=True)
    snap = service.inspect(run)
    assert snap["engine"] == "synthetic"
    assert snap["has"]["energy"] is True
    assert snap["has"]["trajectory"] is True


def test_list_engines_and_cases():
    engines = service.list_engines()
    assert "synthetic" in engines and "gromacs" in engines
    assert "adk_morph" in service.cases()


def test_new_domain_plugs_in_via_adapter():
    """The 'ultimate version' seam: a non-MD domain registers through the same
    EngineAdapter port and is immediately discoverable."""

    class FluidEngine(EngineAdapter):
        name = "fluid-cfd"

        def detect(self, run):
            return bool(next(Path(run).glob("*.foam"), None))

        def load_context(self, run, selection):
            ctx = RunContext(run_dir=Path(run), engine=self.name, selection=selection)
            ctx.extra = {"reynolds": 4500.0}
            return ctx

    register_engine(FluidEngine())
    try:
        assert "fluid-cfd" in service.list_engines()
        d = Path(__file__).parent
        (d / "x.foam").write_text("stub")
        assert isinstance(select_engine(d), FluidEngine)
        (d / "x.foam").unlink()
    finally:
        _ENGINES.pop()
