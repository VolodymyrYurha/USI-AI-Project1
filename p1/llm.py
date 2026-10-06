"""Model calls. Every call to a model in your system goes through `call` (or `call_json`).

`call` counts the calls for the current request and refuses one past the limit: 1 for the single-call variant,
10 for a compound system. It records each call (prompt, answer, tokens, seconds) in the trace, under the step
that made it.

Settings, from environment variables:
  P1_BACKEND   "course" (the course endpoint, the default), "fake" (no model, for tests), "openai" or "anthropic"
  P1_ENDPOINT  the course endpoint's address, shown on the Project 1 page of the course app
  P1_TOKEN     your own token, made on that page; your calls are paid from your team's budget
  P1_MODEL     leave it unset for the course endpoint, which runs only the course model

For the openai backend (any OpenAI-compatible chat completions API; course staff use it to compare models):
  OPENAI_API_KEY, or P1_OPENAI_KEY_FILE  the key, or a file that holds it
  P1_BASE_URL          default https://api.openai.com/v1
  P1_REASONING_EFFORT  optional, passed as reasoning_effort to reasoning models
  P1_EXTRA_TOKENS      optional, added to every call's token limit, for models that reason before answering
"""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from typing import Callable, Optional, TypeVar

from pydantic import BaseModel, ValidationError

from . import trace as _trace

T = TypeVar("T", bound=BaseModel)


class CallLimitError(Exception):
    """The system tried to make more model calls for one request than its variant allows."""


class ModelError(Exception):
    """The model call failed (network, endpoint, or budget)."""

    def __init__(self, message: str, status: Optional[int] = None, refused: bool = False):
        super().__init__(message)
        self.status = status
        self.refused = refused  # the connection was refused, so the request never reached the endpoint


class StepRequiredError(Exception):
    """A compound system made a model call outside a declared step."""


class NeedsLabel(BaseException):
    """While sending step inputs for labeling (`python -m p1.labels send`), a step tried to call the model.
    A BaseException, so that a step's own `except Exception` doesn't hide it."""


def _fake(prompt: str, system: Optional[str]) -> str:
    return json.dumps({"pick": None, "explanation": "fake backend: no model was called"})


# Tests can replace this with a function (prompt, system) -> text.
fake_responder: Callable[[str, Optional[str]], str] = _fake


def _tls_context() -> Optional[ssl.SSLContext]:
    """Certificates from certifi, which pip installs with the starter. Python from python.org on a Mac has no
    certificates of its own until you run its "Install Certificates" script, so without certifi every call fails.
    Without certifi (e.g. on Gradescope), Python's own certificates are used."""
    try:
        import certifi
    except ImportError:
        return None
    return ssl.create_default_context(cafile=certifi.where())


_TLS = _tls_context()


def _post(url: str, headers: dict, body: dict, timeout: float = 120.0) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_TLS) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        try:  # the course endpoint explains its refusals in plain words
            detail = json.loads(detail)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            pass
        raise ModelError(f"HTTP {e.code} from {url}: {detail}", status=e.code) from None
    except (urllib.error.URLError, TimeoutError) as e:
        refused = isinstance(getattr(e, "reason", None), ConnectionRefusedError)
        raise ModelError(f"could not reach {url}: {e}", refused=refused) from None


def check_config() -> str:
    """Raise ModelError if the chosen backend is missing a setting. Returns the backend's name."""
    backend = os.environ.get("P1_BACKEND", "course")
    needs = {"fake": [], "course": ["P1_ENDPOINT", "P1_TOKEN"], "anthropic": ["ANTHROPIC_API_KEY", "P1_MODEL"],
             "openai": ["P1_MODEL"]}
    if backend not in needs:
        raise ModelError(f"unknown P1_BACKEND {backend!r}; use course, fake, openai or anthropic")
    missing = [v for v in needs[backend] if not os.environ.get(v)]
    if backend == "openai" and not _openai_key():
        missing.append("OPENAI_API_KEY (or P1_OPENAI_KEY_FILE)")
    if missing:
        raise ModelError(f"P1_BACKEND={backend} needs {' and '.join(missing)} (see the README), or use P1_BACKEND=fake to test without a model")
    return backend


def _openai_key() -> str:
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"].strip()
    path = os.environ.get("P1_OPENAI_KEY_FILE")
    if path and os.path.exists(os.path.expanduser(path)):
        with open(os.path.expanduser(path), encoding="utf-8") as f:
            return f.read().strip()
    return ""


_OPENAI_REFUSED: dict[str, set] = {}  # model -> request parameters it refused, e.g. temperature for reasoning models


def _openai(prompt: str, system: Optional[str], max_tokens: int, temperature: float, model: str) -> tuple[str, dict]:
    key = _openai_key()
    base = os.environ.get("P1_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    body = {"model": model, "messages": messages, "temperature": temperature,
            "max_completion_tokens": max_tokens + int(os.environ.get("P1_EXTRA_TOKENS", "0") or 0)}
    if os.environ.get("P1_REASONING_EFFORT"):
        body["reasoning_effort"] = os.environ["P1_REASONING_EFFORT"]
    for k in _OPENAI_REFUSED.get(model, ()):
        body.pop(k, None)
    for attempt in range(6):
        try:
            r = _post(base + "/chat/completions", {"authorization": f"Bearer {key}"}, body)
            break
        except ModelError as e:
            msg = str(e).replace(key, "[key]") if key else str(e)
            refused = next((k for k in ("temperature", "reasoning_effort") if k in body and e.status == 400 and k in msg), None)
            if refused:  # the model doesn't take this parameter; drop it for this model and try again
                _OPENAI_REFUSED.setdefault(model, set()).add(refused)
                body.pop(refused)
                continue
            if e.status in (429, 500, 502, 503, 504) and attempt < 5:
                time.sleep(2 ** attempt)
                continue
            raise ModelError(msg, status=e.status) from None
    choice = (r.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content") or ""
    if not text and choice.get("finish_reason") == "length":
        raise ModelError("the model used its whole token limit before answering (set P1_EXTRA_TOKENS for reasoning models)")
    return text, {"backend": "openai", "model": r.get("model"), "usage": r.get("usage")}


def _complete(prompt: str, system: Optional[str], max_tokens: int, temperature: float) -> tuple[str, dict]:
    backend = os.environ.get("P1_BACKEND", "course")
    model = os.environ.get("P1_MODEL", "")
    if backend == "fake":
        return fake_responder(prompt, system), {"backend": "fake"}
    if backend == "course":
        endpoint = os.environ.get("P1_ENDPOINT")
        token = os.environ.get("P1_TOKEN", "").strip()
        if not endpoint or not token:
            raise ModelError("set P1_ENDPOINT and P1_TOKEN (see the README), or P1_BACKEND=fake to test without a model")
        body = {"model": model or None, "system": system, "prompt": prompt, "max_tokens": max_tokens, "temperature": temperature}
        waits = [2, 4, 8, 16, 30]  # about a minute in all, e.g. while the course app restarts
        for attempt in range(len(waits) + 1):
            try:
                r = _post(endpoint.rstrip("/") + "/complete", {"authorization": f"Bearer {token}"}, body)
                break
            except ModelError as e:
                # Busy, too many calls in progress, the app restarting, or the model service failed: nothing was
                # charged, so wait and try again.
                if (e.status in (429, 502, 503, 504) or e.refused) and attempt < len(waits):
                    time.sleep(waits[attempt])
                    continue
                raise
        return r["text"], {"backend": "course", "model": r.get("model"), "usage": r.get("usage"), "cost_usd": r.get("cost_usd"),
                           "budget_left_usd": r.get("budget_left_usd")}
    if backend == "openai":
        if not model or not _openai_key():
            raise ModelError("set P1_MODEL and OPENAI_API_KEY (or P1_OPENAI_KEY_FILE) for the openai backend")
        return _openai(prompt, system, max_tokens, temperature, model)
    if backend == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key or not model:
            raise ModelError("set ANTHROPIC_API_KEY and P1_MODEL for the anthropic backend")
        body = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}]}
        if system:
            body["system"] = system
        r = _post("https://api.anthropic.com/v1/messages", {"x-api-key": key, "anthropic-version": "2023-06-01"}, body)
        text = "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")
        return text, {"backend": "anthropic", "model": r.get("model"), "usage": r.get("usage")}
    raise ModelError(f"unknown P1_BACKEND {backend!r}")


def call(prompt: str, *, system: Optional[str] = None, max_tokens: int = 1000, temperature: float = 0.0) -> str:
    """Call the model once and return its text. Counts toward the per-request limit."""
    t = _trace.current()
    if t is not None and t.labeling:
        if t._stack:
            t._stack[-1]["needs_label"] = True
        raise NeedsLabel(f"request {t.request_id}: no model calls while sending inputs for labeling")
    if t is not None:
        if t.variant == "compound" and not t._stack:
            raise StepRequiredError(f"request {t.request_id}: your system made a model call outside a step. In a compound "
                                    "system, every model call must be inside a function marked with @step.")
        if t.calls >= t.max_calls:
            raise CallLimitError(f"request {t.request_id}: your system tried to make more than {t.max_calls} model "
                                 f"call{'' if t.max_calls == 1 else 's'}, the call limit of the "
                                 f"{'single-call' if t.variant == 'single' else 'compound'} system")
        t.calls += 1
    started = time.time()
    record = {"prompt": prompt, "system": system}
    try:
        text, meta = _complete(prompt, system, max_tokens, temperature)
        record.update(text=text, **meta)
        return text
    except ModelError as e:
        record["error"] = str(e)
        if t is not None:
            t.calls -= 1  # a call that failed doesn't count toward the limit
        raise
    finally:
        record["seconds"] = round(time.time() - started, 3)
        if t is not None:
            if t._stack:
                t._stack[-1]["calls"].append(record)
            else:
                t.records.append({"call": record})


def parse_json(text: str, model: type[T]) -> T:
    """Parse a model's answer into `model`. Accepts the JSON on its own or inside a ```json block."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s.rsplit("```", 1)[0]
    try:
        return model.model_validate_json(s)
    except ValidationError:
        start, end = s.find("{"), s.rfind("}")
        if start != -1 and end > start:
            return model.model_validate_json(s[start:end + 1])
        raise


def call_json(prompt: str, model: type[T], **kw) -> T:
    """Call the model once and parse its answer into `model`. Raises pydantic.ValidationError if it doesn't fit."""
    return parse_json(call(prompt, **kw), model)
