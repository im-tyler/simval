from pathlib import Path

from simval import metadata as M

ROOT = Path(__file__).parent.parent
DATA = Path(__file__).parent / "data"


def test_parse_mdp():
    m = M.parse_mdp(ROOT / "pipeline" / "nvt.mdp")
    assert m["integrator"] == "md"
    assert m["dt"] == "0.002"
    assert m["coulombtype"] == "PME"
    assert m["tcoupl"] == "V-rescale"
    assert m["gen_seed"] == "1729"


def test_extract_force_field_and_water():
    assert M.extract_force_field(DATA / "mini.top") == "amber99sb-ildn.ff"
    assert M.extract_water_model(DATA / "mini.top") == "TIP3P"


def test_render_methods():
    meta = M.build_metadata(
        ROOT / "pipeline" / "nvt.mdp",
        DATA / "mini.top",
        gmx_version="2026.3",
    )
    s = M.render_methods(meta)
    assert "amber99sb-ildn" in s
    assert "TIP3P" in s
    assert "NVT" in s
    assert "V-rescale" in s
    assert "30.0 ps" in s
    assert "1729" in s
    assert "2026.3" in s


def test_render_methods_handles_nve():
    meta = {"mdp": {"integrator": "md", "dt": "0.002", "nsteps": "5000",
                    "tcoupl": "no", "pcoupl": "no", "coulombtype": "PME",
                    "rcoulomb": "1.0", "constraints": "none", "gen_seed": "-1"},
            "force_field": None, "water_model": None, "gmx_version": None}
    s = M.render_methods(meta)
    assert "NVE" in s
    assert "the selected force field" in s
