from __future__ import annotations

import argparse
from pathlib import Path

from simval import __version__
from simval.pipeline import diagnose as run_diagnose


def _safe(fn):
    """Run an engine/oracle call; on a missing/unrecognized run-dir print a clean
    error and return None instead of a traceback."""
    try:
        return fn()
    except (FileNotFoundError, ValueError) as e:
        print(f"simval: error: {e}")
        return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="simval", description="Deterministic MD verification + reference oracle")
    parser.add_argument("--version", action="version", version=f"simval {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("diagnose", help="run diagnostics on a run directory; writes provenance.json")
    d.add_argument("run_dir")
    d.add_argument("--out", default="provenance.json")
    d.add_argument("--selection", default="protein", help="MDAnalysis selection (default: protein)")
    d.add_argument("--thresholds", default=None, help="path to a JSON of per-check threshold overrides")

    ins = sub.add_parser("inspect", help="show engine + what a run-dir contains (no checks)")
    ins.add_argument("run_dir")
    ins.add_argument("--selection", default="protein")

    v = sub.add_parser("validate", help="compare a run against a stored reference case (oracle)")
    v.add_argument("run_dir")
    v.add_argument("--case", required=True)
    v.add_argument("--selection", default=None)

    sub.add_parser("cases", help="list available reference cases")
    sub.add_parser("engines", help="list registered engine adapters")
    cmp = sub.add_parser("compare", help="compare two runs on key metrics (sweep view)")
    cmp.add_argument("run_a")
    cmp.add_argument("run_b")
    cmp.add_argument("--selection", default="protein and name CA")

    sw = sub.add_parser("sweep", help="diagnose every run-dir under a folder; tabulate")
    sw.add_argument("folder")
    sw.add_argument("--baseline", default=None)
    sw.add_argument("--selection", default="protein and name CA")

    vm = sub.add_parser("verify-manifest", help="re-hash files; confirm they match a provenance.json")
    vm.add_argument("manifest")

    ft = sub.add_parser("fetch", help="fetch a structure by PDB ID or UniProt ID (RCSB / AlphaFold DB)")
    ft.add_argument("identifier")
    ft.add_argument("out_dir", nargs="?", default=".")
    ft.add_argument("--source", default=None, choices=["pdb", "alphafold"])

    af = sub.add_parser("afold", help="AlphaFold pLDDT confidence profile for a UniProt id")
    af.add_argument("uniprot_id")
    af.add_argument("out_dir", nargs="?", default=".")

    omx = sub.add_parser("export-omex", help="package a run's provenance + artifacts into a COMBINE archive (.omex)")
    omx.add_argument("run_dir")
    omx.add_argument("out_path", nargs="?", default=None)

    ci = sub.add_parser("case-info", help="show provenance + reference metrics for a stored case")
    ci.add_argument("name")

    args = parser.parse_args(argv)

    if args.cmd == "diagnose":
        overrides = None
        if args.thresholds:
            import json
            overrides = json.loads(Path(args.thresholds).read_text())
        manifest = _safe(lambda: run_diagnose(
            args.run_dir, out=args.out, selection=args.selection, thresholds=overrides))
        if manifest is None:
            return 1
        verdict = manifest["verdict"]
        print(f"simval {__version__} | verdict: {verdict.upper()} | {len(manifest['diagnostics'])} checks")
        for r in manifest["diagnostics"]:
            flag = "PASS" if r["passed"] else "FAIL"
            print(f"  [{flag}] {r['name']:<24} value={r['value']:.4g} threshold={r['threshold']:.4g}")
        return 0 if verdict == "pass" else 1

    if args.cmd == "inspect":
        from simval import service
        snap = _safe(lambda: service.inspect(args.run_dir, selection=args.selection))
        if snap is None:
            return 1
        print(f"simval {__version__} | engine: {snap['engine']} | selection: {snap['selection']}")
        for k, v in snap["has"].items():
            print(f"  {'has' if v else 'no '}  {k}")
        if snap.get("metadata"):
            ff = snap["metadata"].get("force_field") or "-"
            wm = snap["metadata"].get("water_model") or "-"
            print(f"  force_field={ff}  water={wm}")
        return 0

    if args.cmd == "cases":
        from simval.oracle import list_cases
        cases = list_cases()
        print(f"simval {__version__} | {len(cases)} reference cases")
        for name in cases:
            print(f"  {name}")
        return 0

    if args.cmd == "engines":
        from simval import service
        names = service.list_engines()
        print(f"simval {__version__} | {len(names)} engines")
        for name in names:
            print(f"  {name}")
        return 0

    if args.cmd == "compare":
        from simval.compare import compare_runs, largest_deltas
        comp = _safe(lambda: compare_runs(args.run_a, args.run_b, selection=args.selection))
        if comp is None:
            return 1
        print(f"simval {__version__} | compare {args.run_a}  vs  {args.run_b}")
        for name, drel in largest_deltas(comp, n=8):
            a = comp["deltas"][name]["a"]
            b = comp["deltas"][name]["b"]
            print(f"  {name:<24} A={a:.4g}  B={b:.4g}  drel={drel:.3g}")
        return 0

    if args.cmd == "sweep":
        from simval.sweep import KEY_METRICS, sweep
        out = sweep(args.folder, selection=args.selection, baseline=args.baseline)
        print(f"simval {__version__} | sweep {args.folder} | {out['n']} runs")
        keys = [k for k in KEY_METRICS if any(k in r for r in out["runs"])]
        hdr = f"  {'run':<20} " + " ".join(f"{k[:14]:>14}" for k in keys)
        print(hdr)
        base = out.get("baseline") or {}
        for r in out["runs"]:
            if "_error" in r:
                print(f"  {r['run']:<20}  ERROR: {r['_error']}")
                continue
            cells = []
            for k in keys:
                v = r.get(k)
                if v is None:
                    cells.append(f"{'-':>14}")
                elif base and k in base:
                    d = (v - base[k]) / (abs(base[k]) + 1e-12)
                    cells.append(f"{v:>9.3g}({d:+.0%})")
                else:
                    cells.append(f"{v:>14.3g}")
            print(f"  {r['run']:<20} " + " ".join(cells))
        return 0

    if args.cmd == "verify-manifest":
        from simval.manifest import verify_manifest
        out = verify_manifest(args.manifest)
        verdict = "OK" if out["ok"] else "MISMATCH"
        print(f"simval {__version__} | manifest {verdict} | "
              f"{len(out['verified'])} verified, {len(out['tampered'])} tampered, {len(out['missing'])} missing "
              f"(original verdict: {out['verdict']})")
        for f in out["tampered"]:
            print(f"  [TAMPERED] {f}")
        for f in out["missing"]:
            print(f"  [MISSING]  {f}")
        return 0 if out["ok"] else 1

    if args.cmd == "fetch":
        from simval.fetch import fetch_structure
        info = _safe(lambda: fetch_structure(args.identifier, args.out_dir, source=args.source))
        if info is None:
            return 1
        print(f"simval {__version__} | fetched {info['id']} from {info['source']} -> {info['path']} ({info['bytes']} bytes)")
        return 0

    if args.cmd == "afold":
        from simval.afold import check_plddt_profile, fetch_plddt
        fetched = _safe(lambda: fetch_plddt(args.uniprot_id, args.out_dir))
        if fetched is None:
            return 1
        plddt, path = fetched
        r = check_plddt_profile(plddt)
        flag = "CONFIDENT" if r.passed else "LOW-CONFIDENCE"
        print(f"simval {__version__} | AlphaFold pLDDT {args.uniprot_id} | {flag}")
        print(f"  mean pLDDT={r.detail['mean_plddt']:.1f}  residues={r.detail['n_residues']}")
        print(f"  <50: {r.detail['fraction_below_50']*100:.1f}%  <70: {r.detail['fraction_below_70']*100:.1f}%  >90: {r.detail['fraction_above_90']*100:.1f}%")
        if r.detail["low_confidence_residue_indices"]:
            print(f"  low-confidence residues: {r.detail['low_confidence_residue_indices'][:20]}")
        return 0 if r.passed else 1

    if args.cmd == "export-omex":
        from simval.omex import export_omex
        out_path = args.out_path or f"{Path(args.run_dir).name}.omex"
        info = _safe(lambda: export_omex(args.run_dir, out_path))
        if info is None:
            return 1
        print(f"simval {__version__} | OMEX archive -> {info['path']} ({info['bytes']} bytes, {len(info['entries'])} entries)")
        return 0

    if args.cmd == "case-info":
        from simval.oracle import get_case
        case = _safe(lambda: get_case(args.name))
        if case is None:
            return 1
        print(f"simval {__version__} | case: {case.name}")
        print(f"  engine: {case.engine}  | ff: {case.force_field} | selection: {case.selection}")
        print(f"  description: {case.description}")
        print(f"  source: {case.source}")
        print(f"  reference metrics: {case.reference_metrics}")
        print(f"  tolerances: {case.tolerances or '(defaults)'}")
        return 0

    if args.cmd == "validate":
        from simval.oracle import validate as oracle_validate
        result = _safe(lambda: oracle_validate(args.run_dir, args.case, selection=args.selection))
        if result is None:
            return 1
        verdict = "MATCH" if result.passed else "DRIFT"
        print(f"simval {__version__} | oracle case={args.case} | {verdict} | "
              f"{result.detail['n_checked']} metrics, {result.detail['n_failed']} drifted")
        for name, m in result.detail["metrics"].items():
            flag = "ok" if m["passed"] else "DRIFT"
            print(f"  [{flag}] {name:<24} ref={m['reference']:.4g} cand={m['candidate']:.4g} "
                  f"drel={m['delta_rel']:.3g} ({m['tol_kind']})")
        return 0 if result.passed else 1
    return 0
