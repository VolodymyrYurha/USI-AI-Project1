"""Declared steps: the building blocks of a compound system.

A step is a function that takes one pydantic model and returns one pydantic model. Declaring it with `@step` does
three things on every call:

1. It checks the input and the output against the declared types. A mismatch raises ContractError, so a broken
   output is caught at the step that produced it, not at the end.
2. It records the step's input, output and time in the trace, along with the model calls made inside it.
3. It lets `p1.run --override STEP=labels.jsonl` replace the step's output with a correct output you labeled by hand
   (the swap-in test), so you can see whether the steps after it get the answer right. A label is matched to the
   call with the same input, so a step that runs several times for one request (e.g., once per candidate) gets the
   right label for each call. A call with no matching label runs as usual.

Example:

    class Summary(BaseModel):
        text: str

    @step
    def summarize(request: Request) -> Summary:
        return Summary(text=call(f"Summarize: {request.request}"))

Step names must be unique in your system; by default the name is the function's name.
"""
from __future__ import annotations

import functools
import inspect
import types as _pytypes
import time
import typing
from typing import Any, Callable, Optional

from pydantic import BaseModel, ValidationError

from . import llm as _llm
from . import trace as _trace


REGISTRY: dict[str, Callable] = {}  # step name -> declared step, filled as your system's module is imported


class ContractError(Exception):
    """A step received or returned something that doesn't match its declared type."""


def _model_type(annotation: Any, where: str, fn: Callable) -> type[BaseModel]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    raise TypeError(f"step {fn.__name__}: the {where} must be annotated with a pydantic model, got {annotation!r}")


def _dump(value: Any) -> Any:
    return value.model_dump(mode="json") if isinstance(value, BaseModel) else value


def _labeled_output(t, step_name: str, dumped_input: Any):
    """The swap-in output for this call, or None to run the step. Labels in a list are used in call order; labels
    in a dict are matched by the call's input, so a call with no label runs the step as usual."""
    if t is None or not t.overrides.get(step_name):
        return None
    labels = t.overrides[step_name]
    if isinstance(labels, dict):
        key = _trace.input_key(dumped_input)
        if key in labels:
            t.used.add((step_name, key))
            return labels[key]
        return None
    return labels.pop(0)


def stand_in(model: type[BaseModel]) -> BaseModel:
    """The simplest value of an output type: defaults where there are some, else the first choice, false, 0, "",
    none or an empty list. Used only while sending inputs for labeling; it is never sent or graded."""
    def value(tp: Any) -> Any:
        origin, args = typing.get_origin(tp), typing.get_args(tp)
        if origin is typing.Literal:
            return args[0]
        if origin in (typing.Union, _pytypes.UnionType):
            return None if type(None) in args else value(args[0])
        if origin in (list, set, frozenset, tuple) or tp in (list, set, tuple):
            return []
        if origin is dict or tp is dict:
            return {}
        if isinstance(tp, type) and issubclass(tp, BaseModel):
            return fill(tp)
        return {bool: False, int: 0, float: 0.0, str: ""}.get(tp)

    def fill(m: type[BaseModel]) -> dict:
        return {name: value(f.annotation) for name, f in m.model_fields.items() if f.is_required()}

    return model.model_validate(fill(model))


def step(fn: Optional[Callable] = None, *, name: Optional[str] = None):
    """Declare a step. Use as `@step` or `@step(name="check_candidates")`."""
    def wrap(f: Callable):
        hints = typing.get_type_hints(f)
        params = list(inspect.signature(f).parameters)
        if len(params) != 1:
            raise TypeError(f"step {f.__name__}: a step takes exactly one argument (a pydantic model)")
        in_type = _model_type(hints.get(params[0]), "input", f)
        out_type = _model_type(hints.get("return"), "return type", f)
        step_name = name or f.__name__
        if step_name in REGISTRY and REGISTRY[step_name].__qualname__ != f.__qualname__:
            raise TypeError(f"two steps are named {step_name!r}; give one of them another name with @step(name=...)")

        @functools.wraps(f)
        def run(value: Any):
            t = _trace.current()
            try:
                value = value if isinstance(value, in_type) else in_type.model_validate(_dump(value))
            except ValidationError as e:
                if t is not None:
                    t.records.append({"step": step_name, "parent": t.current_step(), "input": _dump(value),
                                      "error": f"input contract: {e.errors()[:3]}"})
                raise ContractError(f'the input to your "{step_name}" step doesn\'t fit its input type, '
                                    f'{in_type.__name__}: {e}') from None
            record = {"step": step_name, "parent": t.current_step() if t else None, "input": _dump(value), "calls": []}
            if t is not None:
                record["seq"] = t.seq
                t.seq += 1
                t.output_types[step_name] = out_type
            labeled = _labeled_output(t, step_name, record["input"])
            if labeled is not None:
                out = out_type.model_validate(labeled)
                record.update(output=_dump(out), overridden=True, seconds=0.0)
                t.records.append(record)
                return out
            if t is not None:
                t._stack.append(record)
            started = time.time()
            try:
                out = f(value)
            except _llm.NeedsLabel as needs:
                if t is None or not record.get("needs_label"):
                    raise
                # Sending inputs for labeling: go on with a stand-in output, so the run reaches the step's next calls.
                try:
                    out = stand_in(out_type)
                except Exception:
                    record["stand_in"] = "failed"  # the input is still recorded; the request stops here
                    t.records.append(record)
                    raise needs from None
                record["stand_in"] = True
            except Exception as e:
                record["error"] = f"{type(e).__name__}: {e}"
                if t is not None:
                    t.records.append(record)
                raise
            finally:
                if t is not None:
                    t._stack.pop()
                record["seconds"] = round(time.time() - started, 3)
            try:
                out = out if isinstance(out, out_type) else out_type.model_validate(_dump(out))
            except ValidationError as e:
                record["error"] = f"output contract: {e.errors()[:3]}"
                if t is not None:
                    t.records.append(record)
                raise ContractError(f'your "{step_name}" step returned an output that doesn\'t fit its output type, '
                                    f'{out_type.__name__}: {e}') from None
            record["output"] = _dump(out)
            if t is not None:
                t.records.append(record)
            return out

        run.step_name = step_name
        run.input_type = in_type
        run.output_type = out_type
        REGISTRY[step_name] = run
        return run

    return wrap(fn) if fn is not None else wrap
