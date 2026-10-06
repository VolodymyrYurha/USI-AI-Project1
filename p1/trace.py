"""The trace: a record of every step and every model call for one request.

`p1.run` opens one trace per request. Steps (`p1.steps.step`) and model calls (`p1.llm.call`) add records to the
current trace, and `p1.run` writes it to traces.jsonl. You don't call anything here yourself.
"""
from __future__ import annotations

import contextvars
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Trace:
    request_id: str
    variant: str                                  # "single" or "compound"
    max_calls: int                                # 1 for the single-call variant, 10 for a compound system
    # Swap-in: step name -> correct outputs. A list is used in call order; a dict maps input_key(input) -> output.
    overrides: dict[str, Any] = field(default_factory=dict)
    used: set = field(default_factory=set)  # (step, input key) pairs of dict overrides that were used
    records: list[dict] = field(default_factory=list)
    calls: int = 0
    # `python -m p1.labels send`: model calls aren't made; a step that would call the model records its input instead.
    labeling: bool = False
    seq: int = 0                                  # numbers step calls in the order they start
    output_types: dict = field(default_factory=dict)  # step name -> its output type, for the steps that ran
    started: float = field(default_factory=time.time)
    _stack: list[dict] = field(default_factory=list)

    def current_step(self) -> Optional[str]:
        return self._stack[-1]["step"] if self._stack else None

    def to_json(self) -> dict:
        return {"request_id": self.request_id, "variant": self.variant, "model_calls": self.calls,
                "seconds": round(time.time() - self.started, 3), "records": self.records}


_current: contextvars.ContextVar[Optional[Trace]] = contextvars.ContextVar("p1_trace", default=None)


def input_key(value: Any) -> str:
    """A step input as canonical JSON, for matching labeled outputs to calls by their input. A whole number such as
    1.0 is written as 1, because the course app returns inputs that way, so labels pulled from it match the calls."""
    return json.dumps(_whole_numbers(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _whole_numbers(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {k: _whole_numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_whole_numbers(v) for v in value]
    return value


def current() -> Optional[Trace]:
    return _current.get()


def start(trace: Trace):
    return _current.set(trace)


def finish(token) -> None:
    _current.reset(token)
