"""The course app, for labels: send your model steps' inputs there, and get your team's labels back.

It uses the same settings as model calls: P1_ENDPOINT (shown on the Project 1 page of the course app) and P1_TOKEN.
You don't call anything here yourself; `python -m p1.labels send` and `pull` do.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .llm import ModelError, _post


def _settings() -> tuple[str, str]:
    endpoint = os.environ.get("P1_ENDPOINT", "").rstrip("/")
    token = os.environ.get("P1_TOKEN", "").strip()
    if not endpoint or not token:
        raise SystemExit("set P1_ENDPOINT and P1_TOKEN (see the README): the labels live in the course app")
    return endpoint, token


def get(path: str) -> Any:
    endpoint, token = _settings()
    req = urllib.request.Request(endpoint + path, headers={"authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"the course app said: {_message(e)}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise SystemExit(f"could not reach the course app at {endpoint}: {e}") from None


def post(path: str, body: dict) -> Any:
    endpoint, token = _settings()
    try:
        return _post(endpoint + path, {"authorization": f"Bearer {token}"}, body)
    except ModelError as e:
        raise SystemExit(f"the course app said: {str(e).split(': ', 1)[-1]}") from None


def _message(e: urllib.error.HTTPError) -> str:
    text = e.read().decode(errors="replace")[:500]
    try:
        return json.loads(text)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return f"HTTP {e.code} {text}"


# ---- step output types, from the JSON schema pydantic gives (the course app labels from the same schema) ----

def _resolve(node: Any, defs: dict) -> tuple[dict, bool]:
    """The node with $ref and Optional unwrapped, and whether it may be None."""
    nullable = False
    for _ in range(20):
        if not isinstance(node, dict):
            return {}, nullable
        if "$ref" in node:
            node = {**defs.get(node["$ref"].split("/")[-1], {}), **{k: v for k, v in node.items() if k != "$ref"}}
            continue
        options = node.get("anyOf") or node.get("oneOf")
        if options:
            rest = [o for o in options if not (isinstance(o, dict) and o.get("type") == "null")]
            nullable = nullable or len(rest) < len(options)
            if len(rest) != 1:
                return {}, nullable
            node = {**rest[0], **{k: v for k, v in node.items() if k not in ("anyOf", "oneOf")}}
            continue
        if isinstance(node.get("allOf"), list) and len(node["allOf"]) == 1:
            node = {**node["allOf"][0], **{k: v for k, v in node.items() if k != "allOf"}}
            continue
        return node, nullable
    return {}, nullable


def _free_text(node: dict) -> bool:
    return node.get("type") == "string" and "enum" not in node and "const" not in node


def fill(schema: dict, value: Any, node: Any = None) -> Any:
    """A label from the course app as a whole output: free-text fields, which aren't labeled, get their default,
    or none, or an empty string, so the output fits the step's output type."""
    defs = schema.get("$defs", {})
    node, _ = _resolve(schema if node is None else node, defs)
    if value is None:
        return None
    if node.get("type") == "array" and isinstance(value, list):
        return [fill(schema, v, node.get("items")) for v in value]
    if node.get("type") == "object" and isinstance(value, dict) and isinstance(node.get("properties"), dict):
        out = {}
        for name, prop in node["properties"].items():
            if name in value:
                out[name] = fill(schema, value[name], prop)
                continue
            inner, nullable = _resolve(prop, defs)
            if "default" in prop:
                out[name] = prop["default"]
            elif inner.get("type") == "array":
                out[name] = []
            else:
                out[name] = None if nullable or not _free_text(inner) else ""
        return out
    return value


def labeled_paths(schema: dict) -> list[str]:
    """The fields a label sets, to compare with the step's output: nested objects by dotted path (players.low),
    lists as a whole (in a list of objects, only the parts the label sets are compared)."""
    defs = schema.get("$defs", {})

    def walk(node: Any, prefix: str) -> list[str]:
        node, _ = _resolve(node, defs)
        if node.get("type") == "object" and isinstance(node.get("properties"), dict):
            out = []
            for name, prop in node["properties"].items():
                out += walk(prop, f"{prefix}{name}.")
            return out
        if _free_text(node):
            return []
        if node.get("type") == "array":
            item, _ = _resolve(node.get("items"), defs)
            if _free_text(item) or (item.get("type") == "object" and not walk(item, "")):
                return []
        return [prefix[:-1]]

    return walk(schema, "")
