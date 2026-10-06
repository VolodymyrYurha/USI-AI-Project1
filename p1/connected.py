"""Which of your compound system's model steps are connected. Milestone 2 needs at least 2 connected model steps.

    python -m p1.contracts systems/compound.py

A model step is a step that calls the model. It counts as connected unless we find clear evidence of one of these:
1. Its input is the same on every request we ran, so the step doesn't look at the request or at an earlier step.
2. Changing its output never changes anything after it: not the later steps' inputs, not which steps run, and not
   your system's answer, including its explanation.

We run your system on the 10 public practice requests without the model, so this costs nothing. Where you have a
label for a model step's input (in labels/, from `python -m p1.labels pull`), the label stands in for the model's
answer. Every other model call gets a filler output of the right type, as in `python -m p1.labels send`. Then, one
model step at a time, we change one field of its output, run the request again, and compare everything after it.
We run the same test on Gradescope.
"""
from __future__ import annotations

import copy
import time
import types as _pytypes
import typing
from typing import Any

from pydantic import BaseModel

from . import llm, run
from .steps import stand_in
from . import trace as _trace
from .types import Request

MAX_RUNS = 5000   # reruns in all at most; each takes milliseconds, because no model is called
SECONDS = 90      # for the whole test; a step we couldn't finish testing counts as connected


def _run(system, request: Request, overrides: dict) -> dict:
    """One request without the model: the step records in the order they started, and the final answer or error."""
    t = _trace.Trace(request_id=request.id, variant="compound", max_calls=run.MAX_CALLS["compound"],
                     overrides=copy.deepcopy(overrides), labeling=True)
    token = _trace.start(t)
    try:
        out = system.answer(request)
        end = out.model_dump(mode="json") if isinstance(out, BaseModel) else {"answer": repr(out)}
    except (Exception, llm.NeedsLabel) as e:
        end = {"error": f"{type(e).__name__}: {e}"[:300]}
    finally:
        _trace.finish(token)
    # t.records is in the order the steps finished; keep that order as "_end" to tell a step's own inner steps apart
    records = sorted((dict(r, _end=i) for i, r in enumerate(t.records) if "step" in r), key=lambda r: r.get("seq", 0))
    return {"records": records, "end": end, "types": dict(t.output_types)}


def _is_model_step(rec: dict) -> bool:
    return bool(rec.get("needs_label") or rec.get("overridden"))


def _after(obs: dict, seq: int) -> tuple:
    """Everything that happened after the step call that started at `seq`: each later step with its input, and the
    final answer or error. Steps that ran inside that call (they started after it and finished before it) are left
    out, because they don't run when a label or a changed output stands in for the call."""
    me = next((r for r in obs["records"] if r.get("seq") == seq), None)
    inside = (lambda r: me is not None and r["_end"] < me["_end"])
    return (tuple((r["step"], _trace.input_key(r.get("input"))) for r in obs["records"]
                  if r.get("seq", -1) > seq and not inside(r)),
            _trace.input_key(obs["end"]))


def _first_output(name: str, obs: dict) -> dict:
    return next((x["output"] for x in obs["records"] if x["step"] == name and "output" in x), {})


def _alternatives(tp: Any, value: Any) -> list:
    """Other values of type `tp` than `value`, one change at a time. An empty or missing value gets values of the
    type, e.g. a list with one element, so that code that reacts only to a present value runs too."""
    origin, args = typing.get_origin(tp), typing.get_args(tp)
    if origin is typing.Annotated:
        return _alternatives(args[0], value)
    if origin is typing.Literal:
        return [a for a in args if a != value]
    if origin in (typing.Union, _pytypes.UnionType):
        out = [None] if type(None) in args and value is not None else []
        for a in (a for a in args if a is not type(None)):
            out += _alternatives(a, value) if value is not None else [_filler(a)] + _alternatives(a, _filler(a))[:3]
        return out
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        value = value if value else _filler(tp)
        return ([value] if value != {} else []) + [dict(value, **{k: v}) for k, v in _field_changes(tp, value)][:12]
    if tp is bool:
        return [not value]
    if tp is int:
        return [v for v in (0, 1, (value or 0) + 1, (value or 0) - 1) if v != value]
    if tp is float:
        return [v for v in (0.0, 1.0, (value or 0.0) + 1.0) if v != value]
    if tp is str:
        return [v for v in ("", "something else") if v != value]
    if origin in (list, set, frozenset, tuple) or tp in (list, set, tuple):
        elem = args[0] if args else Any
        value = list(value or [])
        if not value:
            return [[v] for v in ([_filler(elem)] + _alternatives(elem, _filler(elem)))[:6]]
        out = [[]]
        if len(value) > 1:
            out += [value[::-1], value[:-1]]
        return out + [value + value[-1:]]
    if origin is dict or tp is dict:
        return [{}] if value else []
    return []


def _filler(tp: Any) -> Any:
    """The simplest valid value of a type, as in `python -m p1.labels send`."""
    origin, args = typing.get_origin(tp), typing.get_args(tp)
    if origin is typing.Literal:
        return args[0]
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        try:
            return stand_in(tp).model_dump(mode="json")
        except Exception:
            return {}
    if origin in (typing.Union, _pytypes.UnionType):
        return None if type(None) in args else _filler(args[0])
    if origin in (list, set, frozenset, tuple) or tp in (list, set, tuple):
        return []
    return {bool: False, int: 0, float: 0.0, str: ""}.get(tp)


def _field_changes(model: type[BaseModel], value: dict) -> list[tuple[str, Any]]:
    out = []
    for name, f in model.model_fields.items():
        for alt in _alternatives(f.annotation, value.get(name)):
            out.append((name, alt))
    return out


def _swaps(out_type: type[BaseModel], output: dict) -> list[dict]:
    """Valid outputs of the step that differ from `output` in one field (nested fields included)."""
    seen, out = {_trace.input_key(output)}, []
    for name, alt in _field_changes(out_type, output):
        try:
            changed = out_type.model_validate(dict(output, **{name: alt})).model_dump(mode="json")
        except Exception:
            continue
        key = _trace.input_key(changed)
        if key not in seen:
            seen.add(key)
            out.append(changed)
    return out


def check(system, requests: list[Request], overrides: dict, more_steps: set | None = None,
          seconds: float = SECONDS) -> dict:
    """The connected-steps test on `requests`. `overrides` is request id -> step -> {input key: labeled output}.
    `more_steps` are model steps found elsewhere (on Gradescope, in the runs of check 8); without evidence on them,
    they count as connected."""
    deadline = time.time() + seconds
    runs = [0]
    found: dict[str, None] = {}
    types: dict[str, type] = {}
    inputs: dict[str, set] = {}       # step -> each run's inputs to it, in order (not counting runs that changed it)
    ran_on: dict[str, int] = {}       # step -> on how many requests it ran in the normal runs
    places: dict[str, list] = {}      # step -> (request, overrides, run) where it ran, to change its output there

    def over() -> bool:
        return runs[0] >= MAX_RUNS or time.time() > deadline

    def go(r: Request, ov: dict) -> dict:
        runs[0] += 1
        return _run(system, r, ov)

    def note(r: Request, ov: dict, obs: dict, changed: set = frozenset(), normal: bool = False) -> None:
        types.update(obs["types"])
        per_step: dict[str, list] = {}
        for x in obs["records"]:
            if _is_model_step(x):
                found.setdefault(x["step"])  # a step that runs only after a change is a model step too
                per_step.setdefault(x["step"], []).append(_trace.input_key(x.get("input")))
        for name, keys in per_step.items():
            if name not in changed:  # changing a step's own output can change its own later calls; that's no evidence
                inputs.setdefault(name, set()).add(tuple(keys))
            if normal or not places.get(name):
                places.setdefault(name, []).append((r, ov, obs))
            if normal:
                ran_on[name] = ran_on.get(name, 0) + 1

    def changes(name: str, r: Request, ov: dict, obs: dict, also: set = frozenset()):
        """Each rerun with one change to the step's output in this run, and whether anything after the step changed."""
        for rec in [x for x in obs["records"] if x["step"] == name and "output" in x]:
            for alt in _swaps(types[name], rec["output"]):
                if over():
                    return
                ov2 = copy.deepcopy(ov)
                if not isinstance(ov2.get(name, {}), dict):
                    return
                ov2.setdefault(name, {})[_trace.input_key(rec.get("input"))] = alt
                again = go(r, ov2)
                note(r, ov2, again, changed={name} | set(also))
                yield _after(again, rec["seq"]) != _after(obs, rec["seq"])

    for r in requests:
        ov = overrides.get(r.id, {})
        note(r, ov, go(r, ov), normal=True)

    # First, explore: every change to every model step's output, so that steps which run only for some outputs show up
    used, tried, finished = set(), set(), set()
    while not over():
        todo = [n for n in found if n not in tried and types.get(n)]
        if not todo:
            break
        for name in todo:
            tried.add(name)
            for r, ov, obs in list(places.get(name, [])):
                for differs in changes(name, r, ov, obs):
                    if differs:
                        used.add(name)
            if not over():
                finished.add(name)

    # Then, for a step whose changes showed nothing, try again with each other model step's output changed: a later
    # step's output can hide the effect, e.g. a filler that takes a branch which ignores this step
    for name in [n for n in found if n in finished and n not in used]:
        others = [(o, alt) for o in found if o != name and types.get(o) and places.get(o)
                  for alt in _swaps(types[o], _first_output(o, places[o][0][2]))]
        for other, alt in others:
            for r, ov, _ in list(places.get(name, [])):
                if over() or name in used:
                    break
                ov_ctx = copy.deepcopy(ov)
                ov_ctx[other] = [alt] * 100  # this output on every call of that step, whatever its input
                obs = go(r, ov_ctx)
                note(r, ov_ctx, obs, changed={other})
                if any(changes(name, r, ov_ctx, obs, also={other})):
                    used.add(name)
            if over() or name in used:
                break
        if over() and name not in used:
            finished.discard(name)

    unused = sorted(n for n in found if n in finished and n not in used)
    same_input = {n: ran_on[n] for n in found if ran_on.get(n, 0) >= 2 and len(inputs.get(n, ())) == 1}
    for name in sorted(more_steps or ()):
        found.setdefault(name)
    connected = [n for n in found if n not in same_input and n not in unused]
    error = next((o["end"]["error"] for _, _, o in (p for ps in places.values() for p in ps)
                  if "error" in o["end"] and "NeedsLabel" not in o["end"]["error"]), None)
    return {"model_steps": list(found), "connected": connected, "same_input": same_input,
            "unused": unused, "requests": len(requests), "error": error, "reruns": runs[0]}


def lines(result: dict, need: int = 2) -> list[str]:
    """The result in words, the same locally and on Gradescope."""
    found, connected = result["model_steps"], result["connected"]
    out = []
    if not found:
        out.append("We found no model steps: no step tried to call the model on the public practice requests."
                   + (f" Your system raised an error first: {result['error']}" if result.get("error") else ""))
    else:
        out.append(f"We found {len(found)} model step{'' if len(found) == 1 else 's'}: {_names(_q(found))}. "
                   + (f"{'Both' if len(connected) == 2 else 'All ' + str(len(connected))} are connected."
                      if len(connected) == len(found) and len(found) > 1 else
                      f"Connected: {_names(_q(connected)) if connected else 'none'}."))
    for name in found:
        if name in result["same_input"]:
            out.append(f'Your "{name}" step isn\'t connected: its input is the same on all {result["same_input"][name]} '
                       "public practice requests where it ran, so it doesn't look at the request or at an earlier step.")
        elif name in result["unused"]:
            out.append(f'Your "{name}" step isn\'t connected: changing its output never changed anything after it, '
                       "neither the later steps' inputs nor your system's answer, so your system doesn't use its output.")
    if len(connected) < need:
        out.append(f"A compound system must have at least {need} connected model steps.")
    return out


def _q(names) -> list:
    return [f'"{n}"' for n in names]


def _names(items) -> str:
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def overrides_from_dir(labels_dir: str, ids: set) -> dict:
    """request id -> step -> {input key: output}, from the label files `python -m p1.labels pull` writes."""
    from pathlib import Path

    from .io import read_jsonl
    out: dict = {}
    folder = Path(labels_dir)
    if not folder.is_dir():
        return out
    for path in sorted(folder.glob("*.jsonl")):
        for row in read_jsonl(path):
            if row.get("id") in ids:
                out.setdefault(row["id"], {}).setdefault(path.stem, {})[_trace.input_key(row["input"])] = row["output"]
    return out
