"""Tests for the starter code. They use the fake backend, so no model is called.

Run: python -m pytest tests
"""
import json
import os
from pathlib import Path

import pytest

from p1 import contracts, labels, llm, run
from p1.io import read_jsonl, write_jsonl
from p1.types import Request
from tests import toy_systems

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "public.jsonl"


@pytest.fixture(autouse=True)
def fake_backend(monkeypatch):
    monkeypatch.setenv("P1_BACKEND", "fake")
    monkeypatch.setattr(llm, "fake_responder", llm._fake)


@pytest.fixture
def requests():
    return [Request.model_validate(r) for r in list(read_jsonl(DATA))[:5]]


def run_system(system, reqs, tmp_path, overrides=None):
    results = [run.run_one(system, r, (overrides or {}).get(r.id, {})) for r in reqs]
    write_jsonl(tmp_path / "answers.jsonl", (a for a, _ in results))
    write_jsonl(tmp_path / "traces.jsonl", (t for _, t in results))
    (tmp_path / "summary.json").write_text(json.dumps({"variant": system.VARIANT, "max_calls": run.MAX_CALLS[system.VARIANT],
                                                       "requests": len(results)}))
    return results


def test_public_data_matches_the_types():
    rows = list(read_jsonl(DATA))
    assert len(rows) == 150
    for r in rows:
        req = Request.model_validate(r)
        assert [c.id for c in req.candidates] == ["A", "B", "C", "D", "E"]
    answers = {a["id"]: a["correct"] for a in read_jsonl(ROOT / "data" / "public_answers.jsonl")}
    assert set(answers) == {r["id"] for r in rows}


def filled_single(tmp_path):
    """systems/single.py with instructions written in, as a team would."""
    f = tmp_path / "single.py"
    f.write_text((ROOT / "systems" / "single.py").read_text().replace(
        'INSTRUCTIONS = """"""', 'INSTRUCTIONS = """Pick the game that meets every requirement, or decline."""'))
    return str(f)


def test_baseline_runs_the_whole_cli(tmp_path):
    out = tmp_path / "run"
    run.main([filled_single(tmp_path), "--requests", str(DATA), "--out", str(out), "--limit", "5"])
    assert len(list(read_jsonl(out / "answers.jsonl"))) == 5
    assert all(t["model_calls"] == 1 for t in read_jsonl(out / "traces.jsonl"))
    assert contracts.check(out)["call_limits"] == []
    assert json.loads((out / "summary.json").read_text())["errors"] == 0


def test_single_variant_refuses_a_second_call(requests, tmp_path):
    results = run_system(toy_systems.single_two_calls, requests[:1], tmp_path)
    answer, trace = results[0]
    assert "CallLimitError" in answer["error"]
    assert trace["model_calls"] == 1
    assert contracts.check(tmp_path)["call_limits"][0]["problem"] == "CallLimitError"


def test_compound_limit_is_10_model_calls(requests, tmp_path):
    (tmp_path / "ten").mkdir()
    (tmp_path / "eleven").mkdir()
    answer, trace = run_system(toy_systems.compound_ten_calls, requests[:1], tmp_path / "ten")[0]
    assert answer.get("error") is None and trace["model_calls"] == 10
    answer, trace = run_system(toy_systems.compound_eleven_calls, requests[:1], tmp_path / "eleven")[0]
    assert "CallLimitError" in answer["error"] and trace["model_calls"] == 10
    assert contracts.check(tmp_path / "eleven")["call_limits"][0]["problem"] == "CallLimitError"


def test_contracts_report_shows_two_checks_that_pass_or_fail(requests, tmp_path, capsys):
    ok, bad = tmp_path / "ok", tmp_path / "bad"
    run.main([filled_single(tmp_path), "--requests", str(DATA), "--out", str(ok), "--limit", "2"])
    bad.mkdir()
    run_system(toy_systems.single_two_calls, requests[:1], bad)
    capsys.readouterr()
    with pytest.raises(SystemExit) as done:
        contracts.main([str(ok)])
    said = capsys.readouterr().out
    assert done.value.code == 0
    assert "Call limits: passed" in said and "An answer for every request: passed" in said
    assert "Rule breaks" not in said
    with pytest.raises(SystemExit) as done:
        contracts.main([str(bad)])
    said = capsys.readouterr().out
    assert done.value.code == 1
    assert "Call limits: failed on 1 request" in said
    assert "An answer for every request: failed on 1 request" in said


def test_compound_calls_must_be_inside_a_step(requests, tmp_path):
    answer, _ = run_system(toy_systems.compound_call_outside_step, requests[:1], tmp_path)[0]
    assert "StepRequiredError" in answer["error"]


def test_output_contract_is_checked_and_reported(requests, tmp_path):
    answer, trace = run_system(toy_systems.compound_bad_output, requests[:1], tmp_path)[0]
    assert "ContractError" in answer["error"]
    assert trace["records"][0]["error"].startswith("output contract")
    assert contracts.check(tmp_path)["steps"]["broken"]["output_contract"] == 1


def test_steps_are_traced_with_their_calls(requests, monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "fake_responder", lambda prompt, system: '{"letter": "%s", "fits": %s}' % (prompt[-1], "true" if prompt.endswith("B") else "false"))
    answer, trace = run_system(toy_systems.compound_ok, requests[:1], tmp_path)[0]
    assert answer["pick"] == "B"
    judged = [r for r in trace["records"] if r["step"] == "judge"]
    assert [r["output"]["letter"] for r in judged] == ["A", "B", "C"]
    assert all(len(r["calls"]) == 1 for r in judged)
    assert trace["model_calls"] == 3


def test_swap_in_uses_labels_in_call_order(requests, tmp_path):
    rid = requests[0].id
    labeled = [{"letter": "A", "fits": False}, {"letter": "B", "fits": False}, {"letter": "C", "fits": True}]
    answer, trace = run_system(toy_systems.compound_ok, requests[:1], tmp_path, {rid: {"judge": labeled}})[0]
    assert answer["pick"] == "C"
    assert trace["model_calls"] == 0
    assert all(r.get("overridden") for r in trace["records"] if r["step"] == "judge")


def test_step_accuracy_compares_each_field(requests, monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "fake_responder", lambda prompt, system: '{"letter": "%s", "fits": false}' % prompt[-1])
    run_system(toy_systems.compound_ok, requests[:2], tmp_path)
    n = labels.make(str(tmp_path), "judge", 2, str(tmp_path / "judge.jsonl"))
    assert n == 6
    rows = list(read_jsonl(tmp_path / "judge.jsonl"))
    rows[1]["output"]["fits"] = True  # the hand label disagrees with the system on one call
    write_jsonl(tmp_path / "judge.jsonl", rows)
    r = labels.accuracy(str(tmp_path), "judge", str(tmp_path / "judge.jsonl"))
    assert r["fields"]["letter"]["accuracy"] == 1.0
    assert r["fields"]["fits"]["match"] == 5
    assert r["all_fields_match"] == round(5 / 6, 3)


def test_openai_backend_drops_refused_parameters_and_retries(monkeypatch):
    sent = []

    def fake_post(url, headers, body, timeout=120.0):
        sent.append(dict(body))
        if "temperature" in body:
            raise llm.ModelError('HTTP 400 from x: {"error": {"message": "Unsupported value: temperature"}}', status=400)
        if len(sent) == 2:
            raise llm.ModelError("HTTP 429 from x: slow down", status=429)
        return {"model": "m-1", "choices": [{"message": {"content": "{\"pick\": null, \"explanation\": \"x\"}"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    monkeypatch.setenv("P1_BACKEND", "openai")
    monkeypatch.setenv("P1_MODEL", "m")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "_post", fake_post)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    llm._OPENAI_REFUSED.clear()
    assert llm.check_config() == "openai"
    assert "pick" in llm.call("hello")
    assert "temperature" in sent[0] and "temperature" not in sent[1] and len(sent) == 3
    llm.call("again")  # the refused parameter is remembered for this model
    assert "temperature" not in sent[-1] and len(sent) == 4


def test_openai_backend_needs_a_key(monkeypatch):
    monkeypatch.setenv("P1_BACKEND", "openai")
    monkeypatch.setenv("P1_MODEL", "m")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("P1_OPENAI_KEY_FILE", raising=False)
    with pytest.raises(llm.ModelError):
        llm.check_config()


def test_swap_in_matches_labels_by_input(requests, monkeypatch, tmp_path):
    rid = requests[0].id
    calls = []
    monkeypatch.setattr(llm, "fake_responder", lambda prompt, system: calls.append(prompt) or '{"letter": "B", "fits": true}')
    rows = [{"id": rid, "input": {"letter": "C", "fits": False}, "output": {"letter": "C", "fits": True}},
            {"id": rid, "input": {"letter": "A", "fits": False}, "output": {"letter": "A", "fits": False}}]
    write_jsonl(tmp_path / "judge.jsonl", rows)  # out of call order, and no label for B
    overrides = {k: {"judge": v} for k, v in run.load_overrides(tmp_path / "judge.jsonl").items()}
    answer, trace = run_system(toy_systems.compound_ok, requests[:1], tmp_path, overrides)[0]
    assert len(calls) == 1 and calls[0].endswith("B")  # only the unlabeled call reached the model
    assert answer["pick"] == "B"  # B (model) and C (label) fit; the toy picks the first
    assert trace["unused_overrides"] == {}


def test_course_backend_retries_busy_answers_and_shows_refusals_plainly(monkeypatch):
    import http.server
    import threading

    replies = [(429, {"error": {"code": "busy", "message": "The course model is busy."}}),
               (200, {"text": "{\"pick\": \"B\"}", "model": "gpt-4o-mini-2024-07-18", "cost_usd": 0.0002, "budget_left_usd": 9.9998,
                      "usage": {"prompt_tokens": 10, "completion_tokens": 5}}),
               (402, {"error": {"code": "budget_used_up", "message": "Your team has $0.0001 left."}})]
    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append((self.path, self.headers["authorization"], json.loads(self.rfile.read(int(self.headers["content-length"])))))
            status, body = replies.pop(0)
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("P1_BACKEND", "course")
        monkeypatch.setenv("P1_ENDPOINT", f"http://127.0.0.1:{server.server_port}/api/p1/")
        monkeypatch.setenv("P1_TOKEN", "p1_test-token\n")
        monkeypatch.delenv("P1_MODEL", raising=False)
        monkeypatch.setattr(llm.time, "sleep", lambda s: None)
        assert llm.check_config() == "course"
        assert llm.call("hello", system="be brief", max_tokens=50) == "{\"pick\": \"B\"}"
        assert [s[0] for s in seen] == ["/api/p1/complete", "/api/p1/complete"]
        assert seen[0][1] == "Bearer p1_test-token"
        assert seen[0][2] == {"model": None, "system": "be brief", "prompt": "hello", "max_tokens": 50, "temperature": 0.0}
        with pytest.raises(llm.ModelError) as refused:
            llm.call("again")
        assert refused.value.status == 402 and str(refused.value).endswith("Your team has $0.0001 left.")
        assert len(seen) == 3  # a refusal is not retried
    finally:
        server.shutdown()


def test_course_backend_waits_about_a_minute_while_the_app_is_unreachable(monkeypatch):
    import socket

    with socket.socket() as s:  # a port nothing listens on, so the connection is refused
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setenv("P1_BACKEND", "course")
    monkeypatch.setenv("P1_ENDPOINT", f"http://127.0.0.1:{port}/api/p1")
    monkeypatch.setenv("P1_TOKEN", "p1_test")
    waited = []
    monkeypatch.setattr(llm.time, "sleep", waited.append)
    with pytest.raises(llm.ModelError) as failed:
        llm.call("hello")
    assert failed.value.refused and "could not reach" in str(failed.value)
    assert waited == [2, 4, 8, 16, 30]


def test_a_run_prints_its_cost_and_the_budget_left(monkeypatch, tmp_path, capsys):
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["content-length"]))
            data = json.dumps({"text": "{\"pick\": null, \"explanation\": \"none fits\"}", "model": "m", "cost_usd": 0.0012,
                               "budget_left_usd": 19.5, "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("P1_BACKEND", "course")
        monkeypatch.setenv("P1_ENDPOINT", f"http://127.0.0.1:{server.server_port}/api/p1")
        monkeypatch.setenv("P1_TOKEN", "p1_test")
        run.main([filled_single(tmp_path), "--requests", str(DATA), "--limit", "2", "--out", str(tmp_path / "run")])
    finally:
        server.shutdown()
    said = capsys.readouterr().out
    assert "It made 2 model calls, which cost $0.0024." in said and "Your team's budget left: $19.50" in said


def test_course_backend_needs_the_endpoint_and_token(monkeypatch):
    monkeypatch.setenv("P1_BACKEND", "course")
    monkeypatch.setenv("P1_ENDPOINT", "http://127.0.0.1:9/api/p1")
    monkeypatch.delenv("P1_TOKEN", raising=False)
    with pytest.raises(llm.ModelError, match="P1_TOKEN"):
        llm.check_config()


def test_every_run_records_the_starter_version(tmp_path):
    import p1
    out = tmp_path / "run"
    run.main([filled_single(tmp_path), "--requests", str(DATA), "--limit", "1", "--out", str(out)])
    assert json.loads((out / "summary.json").read_text())["starter_version"] == p1.__version__
    assert p1.__version__.count(".") == 1 and len(p1.__version__) >= 12
