"""Run a system on a file of requests.

    python -m p1.run systems/single.py --requests data/public.jsonl --out runs/single-1

A system is a Python file (or module) that defines:
    VARIANT = "single" or "compound"
    def answer(request: Request) -> Answer

The run writes three files to --out:
    answers.jsonl   one Answer per request, plus "error" if the system failed on it
    traces.jsonl    one trace per request: every step, its input and output, and every model call
    summary.json    counts, time, cost, and the steps your system declares

Swap-in test: `--override STEP=labels.jsonl` replaces the output of STEP with your hand-labeled outputs, for the
requests in the labels file. Use `--ids-from labels.jsonl` to run only those requests (for both the normal run and
the swap-in run, so you compare the same requests).
"""
from __future__ import annotations

import argparse
import copy
import importlib
import importlib.util
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType
from typing import Any

from . import llm
from .version import VERSION as STARTER_VERSION
from . import steps as _steps
from . import trace as _trace
from .io import labels_by_id, read_jsonl, write_jsonl
from .types import Answer, Request

MAX_CALLS = {"single": 1, "compound": 10}


def load_system(spec: str) -> ModuleType:
    sys.path.insert(0, str(Path.cwd()))
    _steps.REGISTRY.clear()
    if spec.endswith(".py"):
        path = Path(spec)
        mod_spec = importlib.util.spec_from_file_location(path.stem, path)
        if mod_spec is None or mod_spec.loader is None:
            raise SystemExit(f"can't load {spec}")
        module = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(module)
    elif spec in sys.modules:
        module = importlib.reload(sys.modules[spec])
    else:
        module = importlib.import_module(spec)
    variant = getattr(module, "VARIANT", None)
    if variant not in MAX_CALLS:
        raise SystemExit(f"{spec}: set VARIANT = \"single\" or \"compound\" (got {variant!r})")
    if not callable(getattr(module, "answer", None)):
        raise SystemExit(f"{spec}: define answer(request: Request) -> Answer")
    return module


def load_overrides(path: str | Path) -> dict[str, Any]:
    """request id -> labels for one step. Rows that record the step's input (as files from `p1.labels pull` do) are
    matched to calls by input; rows without one are used in call order."""
    rows = list(read_jsonl(path))
    if rows and all("input" in r for r in rows):
        out: dict[str, Any] = {}
        for r in rows:
            out.setdefault(r["id"], {})[_trace.input_key(r["input"])] = r["output"]
        return out
    return labels_by_id(path)


def run_one(system: ModuleType, request: Request, overrides: dict[str, Any]) -> tuple[dict, dict]:
    t = _trace.Trace(request_id=request.id, variant=system.VARIANT, max_calls=MAX_CALLS[system.VARIANT],
                     overrides=copy.deepcopy(overrides))
    token = _trace.start(t)
    row: dict = {"id": request.id}
    try:
        out = system.answer(request)
        out = out if isinstance(out, Answer) else Answer.model_validate(out)
        valid = {c.id for c in request.candidates}
        if out.pick is not None and out.pick not in valid:
            letters = "the five letters A to E" if sorted(valid) == list("ABCDE") else "the letters " + ", ".join(sorted(valid))
            raise _steps.ContractError(f"the pick {out.pick!r} isn't one of {letters}")
        row.update(out.model_dump(mode="json"))
    except (Exception, llm.NeedsLabel) as e:  # the run goes on, and the request counts as wrong
        row.update(pick=None, explanation="", error=f"{type(e).__name__}: {e}"[:2000])
    finally:
        _trace.finish(token)
    trace = t.to_json()
    trace["error"] = row.get("error")
    trace["unused_overrides"] = {k: (len([x for x in v if (k, x) not in t.used]) if isinstance(v, dict) else len(v))
                                 for k, v in t.overrides.items() if v}
    trace["unused_overrides"] = {k: n for k, n in trace["unused_overrides"].items() if n}
    return row, trace


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m p1.run", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("system", help="a system file (systems/single.py) or module (systems.single)")
    ap.add_argument("--requests", required=True, help="a requests file, e.g. data/public.jsonl")
    ap.add_argument("--out", required=True, help="a new directory for this run's files")
    ap.add_argument("--limit", type=int, help="run only the first N requests")
    ap.add_argument("--ids-from", help="run only the requests whose ids appear in this JSON Lines file")
    ap.add_argument("--override", action="append", default=[], metavar="STEP=LABELS",
                    help="swap-in: replace STEP's output with the labeled outputs in LABELS (repeatable)")
    ap.add_argument("--workers", type=int, default=4, help="requests to run at the same time (default 4)")
    ap.add_argument("--force", action="store_true", help="overwrite --out if it already has files")
    args = ap.parse_args(argv)

    out = Path(args.out)
    if out.exists() and any(out.iterdir()) and not args.force:
        raise SystemExit(f"{out} already has the results of an earlier run. Choose a new --out folder, or add --force to "
                         "replace them.")
    try:
        backend = llm.check_config()
    except llm.ModelError as e:
        raise SystemExit(str(e)) from None
    system = load_system(args.system)

    requests = [Request.model_validate(r) for r in read_jsonl(args.requests)]
    if args.ids_from:
        wanted = {r["id"] for r in read_jsonl(args.ids_from)}
        requests = [r for r in requests if r.id in wanted]
    if args.limit:
        requests = requests[: args.limit]

    overrides: dict[str, dict[str, list]] = {}  # request id -> step -> outputs
    for item in args.override:
        step_name, sep, path = item.partition("=")
        if not sep:
            raise SystemExit(f"--override {item}: write it as STEP=labels.jsonl")
        if step_name not in _steps.REGISTRY:
            raise SystemExit(f"--override {item}: your system has no step named {step_name!r}; its steps are {sorted(_steps.REGISTRY)}")
        for rid, labels in load_overrides(path).items():
            overrides.setdefault(rid, {})[step_name] = labels

    started = time.time()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        results = list(pool.map(lambda r: run_one(system, r, overrides.get(r.id, {})), requests))

    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "answers.jsonl", (a for a, _ in results))
    write_jsonl(out / "traces.jsonl", (t for _, t in results))
    calls = [t["model_calls"] for _, t in results]
    cost = sum(c.get("cost_usd") or 0 for _, t in results for c in _all_calls(t))
    summary = {
        "system": args.system, "starter_version": STARTER_VERSION, "backend": backend, "model": os.environ.get("P1_MODEL") or None, "variant": system.VARIANT, "max_calls": MAX_CALLS[system.VARIANT],
        "requests_file": args.requests, "requests": len(results),
        "errors": sum(1 for a, _ in results if a.get("error")),
        "declined": sum(1 for a, _ in results if a.get("pick") is None and not a.get("error")),
        "model_calls": {"total": sum(calls), "max_per_request": max(calls, default=0)},
        "cost_usd": round(cost, 4), "seconds": round(time.time() - started, 1),
        "overrides": args.override,
        "steps": {name: {"input": s.input_type.__name__, "output": s.output_type.__name__}
                  for name, s in sorted(_steps.REGISTRY.items())},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Done: {summary['requests']} requests in {summary['seconds']} seconds. Your system declined "
          f"{summary['declined']} and failed on {summary['errors']}. It made {summary['model_calls']['total']} model calls, "
          f"which cost ${cost:.4f}. The results are in {out}/.")
    left = [c["budget_left_usd"] for _, t in results for c in _all_calls(t) if c.get("budget_left_usd") is not None]
    if left:
        print(f"Your team's budget left: ${min(left):.2f}")
    reasons = Counter(a["error"] for a, _ in results if a.get("error"))
    for reason, n in reasons.most_common(3):
        print(f"{n} {'request' if n == 1 else 'requests'} failed: {reason}")
    if len(reasons) > 3:
        print(f"We left out {len(reasons) - 3} other errors here. You find each one in answers.jsonl.")


def _all_calls(trace: dict):
    for rec in trace["records"]:
        if "call" in rec:
            yield rec["call"]
        yield from rec.get("calls", [])


if __name__ == "__main__":
    main()
