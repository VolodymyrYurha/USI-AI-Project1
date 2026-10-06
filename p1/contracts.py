"""Check a run against the Project 1 rules, step by step, or check that your compound system's model steps are
connected.

    python -m p1.contracts runs/compound-1
    python -m p1.contracts systems/compound.py

You get a table with one row per step: how many times the step ran, how many of its inputs and outputs didn't
fit its declared types, how many other errors it raised, and its average model calls and seconds.

Under the table, you see two checks, each passed or failed:
- Call limits: the single-call system makes exactly 1 model call per request, and a compound system at most 10,
  all inside declared steps.
- An answer for every request: your system gives an answer to every request, with no error.

With your compound system instead of a run, you see which of its model steps are connected. Milestone 2 needs at
least 2. We run your system on the 10 public practice requests without the model, with your labels from labels/
(`python -m p1.labels pull`) where you have them; `p1/connected.py` explains the test.

We run the same checks on Gradescope. The command exits with status 1 if a check failed.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from .io import read_jsonl


def check(run_dir: str | Path) -> dict:
    run_dir = Path(run_dir)
    summary = json.loads((run_dir / "summary.json").read_text())
    variant, max_calls = summary["variant"], summary["max_calls"]
    per_step: dict[str, dict] = defaultdict(lambda: {"runs": 0, "input_contract": 0, "output_contract": 0,
                                                    "raised": 0, "overridden": 0, "model_calls": 0, "seconds": 0.0})
    call_limits: list[dict] = []
    no_answer: list[dict] = []
    for tr in read_jsonl(run_dir / "traces.jsonl"):
        rid, calls = tr["request_id"], tr["model_calls"]
        for rec in tr["records"]:
            if "call" in rec:
                if variant == "compound":
                    call_limits.append({"id": rid, "problem": "model call outside a declared step"})
                continue
            s = per_step[rec["step"]]
            s["runs"] += 1
            s["model_calls"] += len(rec.get("calls", []))
            s["seconds"] += rec.get("seconds", 0.0)
            s["overridden"] += bool(rec.get("overridden"))
            err = rec.get("error") or ""
            if err.startswith("input contract"):
                s["input_contract"] += 1
            elif err.startswith("output contract"):
                s["output_contract"] += 1
            elif err:
                s["raised"] += 1
        err = tr.get("error") or ""
        if "CallLimitError" in err or "StepRequiredError" in err:
            call_limits.append({"id": rid, "problem": err.split(":", 1)[0], "detail": err})
        elif variant == "single" and calls != 1 and not err:
            call_limits.append({"id": rid, "problem": f"the single-call variant made {calls} model calls, not 1"})
        elif calls > max_calls:
            call_limits.append({"id": rid, "problem": f"{calls} model calls; the limit is {max_calls}"})
        if err:
            no_answer.append({"id": rid, "error": err[:300]})
    steps = {}
    for name, s in sorted(per_step.items()):
        runs = s["runs"] or 1
        steps[name] = {**s, "seconds": round(s["seconds"] / runs, 3), "model_calls": round(s["model_calls"] / runs, 2)}
    return {"variant": variant, "requests": summary["requests"], "steps": steps,
            "call_limits": call_limits, "no_answer": no_answer}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m p1.contracts", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", help="a run directory written by p1.run, or your compound system, e.g. systems/compound.py")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    ap.add_argument("--requests", default="data/practice.jsonl", help="for a system: the requests (default: %(default)s)")
    ap.add_argument("--labels", default="labels", help="for a system: your pulled labels (default: %(default)s)")
    args = ap.parse_args(argv)
    if args.run.endswith(".py"):
        _check_steps(args)
        return
    r = check(args.run)
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(f"Your {'single-call' if r['variant'] == 'single' else 'compound'} system, on {r['requests']} requests:")
        if r["steps"]:
            print(f"\n{'step':28} {'runs':>5} {'in-err':>6} {'out-err':>7} {'raised':>6} {'swapped':>7} {'calls/run':>9} {'s/run':>6}")
            for name, s in r["steps"].items():
                print(f"{name:28} {s['runs']:>5} {s['input_contract']:>6} {s['output_contract']:>7} {s['raised']:>6} "
                      f"{s['overridden']:>7} {s['model_calls']:>9} {s['seconds']:>6}")
        print()
        _print_check("Call limits", [f"{b['id']}: {b['problem']}" for b in r["call_limits"]])
        _print_check("An answer for every request", [f"{f['id']}: {f['error']}" for f in r["no_answer"]])
    raise SystemExit(1 if r["call_limits"] or r["no_answer"] else 0)


def _check_steps(args) -> None:
    from . import connected, run
    from .types import Request
    system = run.load_system(args.run)
    if system.VARIANT != "compound":
        raise SystemExit(f"only a compound system has steps; this system's VARIANT is {system.VARIANT!r}")
    requests = [Request.model_validate(r) for r in read_jsonl(args.requests)]
    overrides = connected.overrides_from_dir(args.labels, {r.id for r in requests})
    r = connected.check(system, requests, overrides)
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        if not overrides:
            print(f"We found no labels for these requests in {args.labels}/, so we used filler outputs for every model "
                  "call. To use your labels, run `python -m p1.labels pull` first.")
        print("Connected model steps: " + ("passed" if len(r["connected"]) >= 2 else "failed"))
        for line in connected.lines(r):
            print(f"  {line}")
    raise SystemExit(0 if len(r["connected"]) >= 2 else 1)


def _print_check(name: str, problems: list[str]) -> None:
    if not problems:
        print(f"{name}: passed")
        return
    print(f"{name}: failed on {len(problems)} {'request' if len(problems) == 1 else 'requests'}")
    for line in problems[:20]:
        print(f"  {line}")
    if len(problems) > 20:
        print(f"  We left out {len(problems) - 20} more. To see them all, add --json.")


if __name__ == "__main__":
    main()
