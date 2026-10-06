"""Label your model steps in the course app, and measure each step against your labels.

You and your partner label in the course app, on the Labels tab of the Project 1 page. First, send the inputs of
your model steps there. This runs your system without the model (no cost): where a step already has a label, the
label stands in for the model's answer, and every other model step records its input:

    python -m p1.labels send systems/compound.py --requests data/labeling.jsonl

If one model step's input depends on another model step's output, label the earlier step first and run `send`
again: then the later step's inputs are the ones it gets when the earlier step is right.

Second, label each input on the Labels tab. Third, download your team's labels into labels/, one file per step:

    python -m p1.labels pull

Then measure a step against your labels, field by field (on any run of your system on the same requests):

    python -m p1.labels accuracy runs/compound-2 --step my_step --labels labels/my_step.jsonl

And the swap-in test: run the system with your labels in place of the step's outputs, and compare its final answers
with a normal run on the same requests:

    python -m p1.run systems/compound.py --requests data/labeling.jsonl --ids-from labels/my_step.jsonl \\
        --override my_step=labels/my_step.jsonl --out runs/swap-my_step

Each label belongs to one exact input of the step, so a later change to an earlier step only leaves some calls
unlabeled.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from .io import read_jsonl, write_jsonl
from .trace import input_key


def step_outputs(run_dir: str | Path, step: str) -> dict[str, list[dict]]:
    """request id -> the step's records in this run, in call order."""
    out: dict[str, list[dict]] = defaultdict(list)
    for tr in read_jsonl(Path(run_dir) / "traces.jsonl"):
        for rec in tr["records"]:
            if rec.get("step") == step:
                out[tr["request_id"]].append(rec)
    return out


def make(run_dir: str, step: str, n: int, out: str, seed: int = 0) -> int:
    recs = step_outputs(run_dir, step)
    if not recs:
        raise SystemExit(f"no calls of step {step!r} in {run_dir}")
    ids = sorted(recs)
    random.Random(seed).shuffle(ids)
    rows = []
    for rid in sorted(ids[:n]):
        for i, rec in enumerate(recs[rid]):
            rows.append({"id": rid, "call": i, "input": rec.get("input"), "output": rec.get("output"),
                         **({"system_error": rec["error"]} if rec.get("error") else {})})
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(out, rows)
    return len(rows)


def _norm(v):
    if isinstance(v, str):
        return " ".join(v.lower().split())
    if isinstance(v, list) and all(not isinstance(x, (dict, list)) for x in v):
        return sorted((_norm(x) for x in v), key=repr)
    if isinstance(v, list):
        return [_norm(x) for x in v]
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    return v


def _get(value, dotted: str):
    for part in dotted.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def _same(label, actual) -> bool:
    """Whether the output matches the label. In a list of objects, only the keys the label fills in are compared,
    so a quote the label leaves out doesn't count."""
    if isinstance(label, list) and label and all(isinstance(x, dict) for x in label):
        if not isinstance(actual, list):
            return False
        keys = sorted({k for x in label for k, v in x.items() if v is not None})
        pick = lambda xs: sorted((json.dumps(_norm([x.get(k) for k in keys])) for x in xs if isinstance(x, dict)))
        return pick(label) == pick(actual)
    return _norm(actual) == _norm(label)


def accuracy(run_dir: str, step: str, labels: str, fields: list[str] | None = None) -> dict:
    """Compare the step's outputs with the labels, one field at a time. Strings are compared ignoring case and
    spacing, and lists of plain values ignoring order. A label from the course app lists the fields it sets
    ("checked"), and only those are compared, so free text isn't; nested fields are named with dots, e.g. players.low.
    A label that records its input is compared with the call that had the same input. Labels for requests that
    weren't in the run are left out, e.g. labeling requests in a run on the practice requests."""
    got = step_outputs(run_dir, step)
    in_run = {tr["request_id"] for tr in read_jsonl(Path(run_dir) / "traces.jsonl")}
    per_field: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # field -> [matches, compared]
    whole = [0, 0]
    misses = []
    not_in_run = 0
    seen: dict[str, int] = defaultdict(int)
    for row in read_jsonl(labels):
        rid, label = row["id"], row["output"]
        if rid not in in_run:
            not_in_run += 1
            continue
        i = row["call"] if "call" in row else seen[rid]
        seen[rid] += 1
        recs = [r for r in got.get(rid, []) if not r.get("overridden")]
        if "input" in row:  # a label belongs to one input: compare with the call that had it
            key = input_key(row["input"])
            actual = next((r.get("output") for r in recs if input_key(r.get("input")) == key), None)
        else:
            actual = recs[i].get("output") if i < len(recs) else None
        keys = fields or row.get("checked") or list(label)
        ok_all = True
        for k in keys:
            a = None if actual is None else _get(actual, k)
            ok = actual is not None and _same(_get(label, k), a)
            per_field[k][0] += ok
            per_field[k][1] += 1
            if not ok:
                ok_all = False
                misses.append({"id": rid, "call": i, "field": k, "label": _get(label, k), "output": a})
        whole[0] += ok_all
        whole[1] += 1
    return {"step": step, "labeled_calls": whole[1], "labels_not_in_run": not_in_run,
            "all_fields_match": round(whole[0] / whole[1], 3) if whole[1] else None,
            "fields": {k: {"match": m, "of": c, "accuracy": round(m / c, 3)} for k, (m, c) in per_field.items()},
            "misses": misses}


def send(system_spec: str, requests_path: str, limit: int | None = None, out=print) -> dict:
    """Run the system without the model and send the inputs of its model steps to the course app."""
    import copy
    from collections import Counter

    from . import app, llm, run, trace
    from .types import Request

    system = run.load_system(system_spec)
    if system.VARIANT != "compound":
        raise SystemExit("only a compound system has steps to label; this system's VARIANT is " + repr(system.VARIANT))
    overrides = overrides_from(app.get("/labels"))
    requests = [Request.model_validate(r) for r in read_jsonl(requests_path)][:limit]
    items, waiting, output_types = [], Counter(), {}
    for request in requests:
        t = trace.Trace(request_id=request.id, variant="compound", max_calls=run.MAX_CALLS["compound"],
                        overrides=copy.deepcopy(overrides.get(request.id, {})), labeling=True)
        token = trace.start(t)
        try:
            system.answer(request)
        except (Exception, llm.NeedsLabel):
            pass  # a stand-in output can break later code; the inputs recorded before that still count
        finally:
            trace.finish(token)
        output_types.update(t.output_types)
        model_calls = sorted((r for r in t.records if r.get("needs_label") or r.get("overridden")), key=lambda r: r.get("seq", 0))
        unlabeled_before: set[str] = set()   # steps whose stand-in outputs the later calls may depend on
        per_step: Counter = Counter()
        for rec in model_calls:
            blocked = unlabeled_before - {rec["step"]}
            if blocked:
                waiting[(rec["step"], ", ".join(sorted(blocked)))] += 1
                continue
            # The input as the step got it, in its fields' order; the app identifies it whatever the order.
            items.append({"step": rec["step"], "request_id": request.id, "call": per_step[rec["step"]],
                          "input": json.dumps(rec["input"], ensure_ascii=False)})
            per_step[rec["step"]] += 1
            if not rec.get("overridden"):
                unlabeled_before.add(rec["step"])
    if not items:
        out("We sent nothing, because your system made no model call inside a step. In a compound system, every model "
            "call must be inside a function marked with @step.")
        return {"sent": 0}
    schemas = {name: output_types[name].model_json_schema() for name in sorted({i["step"] for i in items})}
    added = 0
    for start in range(0, len(items), 2000):
        added += app.post("/label-items", {"steps": schemas, "items": items[start:start + 2000]})["added"]
    by_step = Counter(i["step"] for i in items)
    labeled = sum(1 for i in items if trace.input_key(json.loads(i["input"])) in overrides.get(i["request_id"], {}).get(i["step"], {}))
    parts = [f'{v} for your "{k}" step' for k, v in by_step.items()]  # in the order the steps first ran
    per_step = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    said = f"We sent {len(items)} inputs from {len(requests)} requests to the course app: {per_step}. "
    if labeled == len(items):
        said += f"All {len(items)} already have a label." if len(items) > 1 else "It already has a label."
    else:
        said += (f"{labeled} of them already have a label. " if labeled else "None of them has a label yet. ") \
            + f"You still have to label {'the other ' if labeled else ''}{len(items) - labeled}, on the Labels tab of the Project 1 page."
    out(said)
    for (step_name, before), n in sorted(waiting.items()):
        out(f'We didn\'t send the inputs of {n} {"call" if n == 1 else "calls"} to your "{step_name}" step yet, because '
            f'they may depend on the outputs of your "{before}" step, and you haven\'t labeled those yet. Label your '
            f'"{before}" step, then run this command again.')
    return {"sent": len(items), "added": added, "waiting": sum(waiting.values())}


def overrides_from(pulled: dict) -> dict:
    """request id -> step -> {input key: whole output}, from the labels the course app returns."""
    from .app import fill
    out: dict = {}
    for row in pulled.get("labels", []):
        schema = pulled["steps"].get(row["step"], {})
        out.setdefault(row["id"], {}).setdefault(row["step"], {})[input_key(row["input"])] = fill(schema, row["label"])
    return out


def pull(out_dir: str = "labels", out=print) -> dict:
    """Write the team's current labels from the course app to out_dir/<step>.jsonl, one file per step."""
    from .app import fill, get, labeled_paths
    pulled = get("/labels")
    by_step: dict[str, list] = defaultdict(list)
    old = defaultdict(int)
    for row in pulled.get("labels", []):
        if not row.get("current"):
            old[row["step"]] += 1
            continue
        schema = pulled["steps"][row["step"]]
        by_step[row["step"]].append({"id": row["id"], "call": row["call"], "input": row["input"],
                                     "output": fill(schema, row["label"]), "checked": labeled_paths(schema),
                                     "saved_by": row.get("saved_by")})
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    for step_name, rows in sorted(by_step.items()):
        path = Path(out_dir) / f"{step_name}.jsonl"
        write_jsonl(path, rows)
        n, ids = len(rows), len({r['id'] for r in rows})
        said = (f'We saved {n} label{"" if n == 1 else "s"} for your "{step_name}" step, on {ids} '
                f'request{"" if ids == 1 else "s"}, in {path}.')
        if old[step_name]:
            said += (f" We left out {old[step_name]} older label{'' if old[step_name] == 1 else 's'}, because your current "
                     "code no longer sends their inputs.")
        out(said)
    if not by_step:
        out("Your team has no labels yet. Send inputs with `python -m p1.labels send`, then label them in the course app.")
    return {step_name: len(rows) for step_name, rows in by_step.items()}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m p1.labels", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    se = sub.add_parser("send", help="send your model steps' inputs to the course app, to label there")
    se.add_argument("system", help="your compound system, e.g. systems/compound.py")
    se.add_argument("--requests", required=True, help="e.g. data/labeling.jsonl")
    se.add_argument("--limit", type=int, help="send only the first N requests")
    pu = sub.add_parser("pull", help="download your team's labels into labels/")
    pu.add_argument("--out", default="labels", help="the directory to write (default labels/)")
    m = sub.add_parser("make", help=argparse.SUPPRESS)
    m.add_argument("run")
    m.add_argument("--step", required=True)
    m.add_argument("--n", type=int, default=20, help="how many requests (default 20)")
    m.add_argument("--seed", type=int, default=0, help="which random requests to pick")
    m.add_argument("--out", required=True)
    a = sub.add_parser("accuracy", help="compare a run's step outputs with your labels")
    a.add_argument("run")
    a.add_argument("--step", required=True)
    a.add_argument("--labels", required=True)
    a.add_argument("--fields", help="comma-separated fields to compare (default: every field in the labels)")
    a.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "send":
        send(args.system, args.requests, args.limit)
        return
    if args.cmd == "pull":
        pull(args.out)
        return
    if args.cmd == "make":
        n = make(args.run, args.step, args.n, args.out, args.seed)
        print(f"wrote {n} lines to {args.out}. Now correct each \"output\" by hand.")
        return
    r = accuracy(args.run, args.step, args.labels, args.fields.split(",") if args.fields else None)
    if args.json:
        print(json.dumps(r, indent=2))
        return
    print(f'Your "{r["step"]}" step: we compared {r["labeled_calls"]} calls with your labels. In {r["all_fields_match"]} '
          f'of them, every labeled field is right.')
    if r["labels_not_in_run"]:
        print(f"We left out {r['labels_not_in_run']} labels for requests that weren't in this run.")
    for k, f in r["fields"].items():
        print(f"  {k:24} {f['match']:>3} of {f['of']:<3} {f['accuracy']}")
    for x in r["misses"][:15]:
        print(f'  Wrong: {x["id"]}, call {x["call"]}, field "{x["field"]}": your label is {json.dumps(x["label"])[:80]}, '
              f'and the step returned {json.dumps(x["output"])[:80]}.')


if __name__ == "__main__":
    main()
