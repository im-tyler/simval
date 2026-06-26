from __future__ import annotations

import argparse

from simval import __version__
from simval.pipeline import diagnose as run_diagnose


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="simval", description="Deterministic MD verification + reference oracle")
    sub = parser.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("diagnose", help="run diagnostics on a run directory; writes provenance.json")
    d.add_argument("run_dir")
    d.add_argument("--out", default="provenance.json")
    d.add_argument("--selection", default="protein", help="MDAnalysis selection (default: protein)")

    v = sub.add_parser("validate", help="compare a run against a stored reference case (oracle)")
    v.add_argument("run_dir")
    v.add_argument("--case", required=True)
    v.add_argument("--selection", default=None)

    c = sub.add_parser("cases", help="list available reference cases")
    e = sub.add_parser("engines", help="list registered engine adapters")

    args = parser.parse_args(argv)

    if args.cmd == "diagnose":
        manifest = run_diagnose(args.run_dir, out=args.out, selection=args.selection)
        verdict = manifest["verdict"]
        print(f"simval {__version__} | verdict: {verdict.upper()} | {len(manifest['diagnostics'])} checks")
        for r in manifest["diagnostics"]:
            flag = "PASS" if r["passed"] else "FAIL"
            print(f"  [{flag}] {r['name']:<24} value={r['value']:.4g} threshold={r['threshold']:.4g}")
        return 0 if verdict == "pass" else 1

    if args.cmd == "cases":
        from simval.oracle import list_cases
        cases = list_cases()
        print(f"simval {__version__} | {len(cases)} reference cases")
        for name in cases:
            print(f"  {name}")
        return 0

    if args.cmd == "engines":
        from simval.context import _ENGINES
        print(f"simval {__version__} | {len(_ENGINES)} engines")
        for eng in _ENGINES:
            print(f"  {eng.name}")
        return 0

    if args.cmd == "validate":
        from simval.oracle import validate as oracle_validate
        result = oracle_validate(args.run_dir, args.case, selection=args.selection)
        verdict = "MATCH" if result.passed else "DRIFT"
        print(f"simval {__version__} | oracle case={args.case} | {verdict} | "
              f"{result.detail['n_checked']} metrics, {result.detail['n_failed']} drifted")
        for name, m in result.detail["metrics"].items():
            flag = "ok" if m["passed"] else "DRIFT"
            print(f"  [{flag}] {name:<24} ref={m['reference']:.4g} cand={m['candidate']:.4g} "
                  f"drel={m['delta_rel']:.3g} ({m['tol_kind']})")
        return 0 if result.passed else 1
    return 0
