"""Tests for p1.connected: which model steps count as connected. No model is called."""
import types
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

from p1 import Answer, Request, call_json, connected, step
from p1.io import read_jsonl

ROOT = Path(__file__).resolve().parent.parent
PRACTICE = [Request.model_validate(r) for r in read_jsonl(ROOT / "data" / "practice.jsonl")]


def system(answer):
    return types.SimpleNamespace(VARIANT="compound", answer=answer)


class Choice(BaseModel):
    pick: Optional[Literal["A", "B", "C", "D", "E"]]
    explanation: str


class Needs(BaseModel):
    players: Optional[int]
    summary: str


class Wanted(BaseModel):
    summary: str
    request: Request


class Ping(BaseModel):
    n: int


class Pong(BaseModel):
    ok: bool


class Sure(BaseModel):
    sure: bool
    pick: Optional[Literal["A", "B", "C", "D", "E"]]


class Kind(BaseModel):
    kind: Literal["play", "gift", "decline"]


@step
def t_decide(request: Request) -> Choice:
    return call_json(f"pick: {request.request}", Choice)


@step
def t_recheck(p: Ping) -> Pong:
    return call_json(f"Reply yes ({p.n})", Pong)


@step
def t_needs(request: Request) -> Needs:
    return call_json(f"needs: {request.request}", Needs)


@step
def t_pick_for(w: Wanted) -> Choice:
    return call_json(f"pick for {w.summary}", Choice)


@step
def t_first(request: Request) -> Sure:
    return call_json(f"first: {request.request}", Sure)


@step
def t_second(request: Request) -> Choice:
    return call_json(f"second: {request.request}", Choice)


@step
def t_kind(request: Request) -> Kind:
    return call_json(f"kind: {request.request}", Kind)


@step
def t_count(request: Request) -> Ping:
    return Ping(n=len(request.candidates))


@step
def t_wrapped(request: Request) -> Pong:
    t_count(request)  # an inner code step, before the model call
    return call_json(f"wrapped: {request.request}", Pong)


def answer_of(choice: Choice) -> Answer:
    return Answer(pick=choice.pick, explanation=choice.explanation)


def test_a_pointless_second_step_isnt_connected():
    def answer(request):
        choice = t_decide(request)
        t_recheck(Ping(n=0))
        return answer_of(choice)
    r = connected.check(system(answer), PRACTICE, {})
    assert r["model_steps"] == ["t_decide", "t_recheck"]
    assert r["connected"] == ["t_decide"]
    assert r["same_input"] == {"t_recheck": 10} and r["unused"] == ["t_recheck"]
    said = connected.lines(r)
    assert 'Your "t_recheck" step isn\'t connected: its input is the same on all 10 public practice requests' in said[1]
    assert said[-1] == "A compound system must have at least 2 connected model steps."


def test_a_step_whose_output_is_ignored_isnt_connected_even_if_its_input_changes():
    def answer(request):
        choice = t_decide(request)
        t_recheck(Ping(n=len(request.request)))
        return answer_of(choice)
    r = connected.check(system(answer), PRACTICE, {})
    assert r["same_input"] == {} and r["unused"] == ["t_recheck"] and r["connected"] == ["t_decide"]
    assert "changing its output never changed anything after it" in connected.lines(r)[1]


def test_free_text_handed_to_the_next_step_connects_it():
    def answer(request):
        needs = t_needs(request)  # the code never reads `players`
        return answer_of(t_pick_for(Wanted(summary=needs.summary, request=request)))
    r = connected.check(system(answer), PRACTICE, {})
    assert r["connected"] == ["t_needs", "t_pick_for"]
    assert connected.lines(r) == ['We found 2 model steps: "t_needs" and "t_pick_for". Both are connected.']


def test_a_step_that_runs_only_when_the_first_is_unsure_is_found_and_connected():
    def answer(request):
        first = t_first(request)
        if first.sure:
            return Answer(pick=first.pick, explanation="sure")
        return answer_of(t_second(request))
    # Labels say the first step is sure on every practice request, so the second step never runs on them
    labels = {r.id: {"t_first": {connected._trace.input_key(r.model_dump(mode="json")): {"sure": True, "pick": "A"}}}
              for r in PRACTICE}
    r = connected.check(system(answer), PRACTICE, labels)
    assert r["model_steps"] == ["t_first", "t_second"] and r["connected"] == ["t_first", "t_second"]


def test_two_steps_that_each_feed_the_answer_are_both_connected():
    def answer(request):
        kind, choice = t_kind(request), t_decide(request)
        return Answer(pick=None, explanation="no") if kind.kind == "decline" else answer_of(choice)
    r = connected.check(system(answer), PRACTICE, {})
    assert r["connected"] == ["t_kind", "t_decide"]


def test_inner_steps_dont_make_an_unused_step_look_connected():
    def answer(request):
        choice = t_decide(request)
        t_wrapped(request)
        return answer_of(choice)
    r = connected.check(system(answer), PRACTICE, {})
    assert "t_wrapped" in r["unused"] and r["connected"] == ["t_decide"]


def test_steps_found_elsewhere_count_as_connected():
    def answer(request):
        return answer_of(t_decide(request))
    r = connected.check(system(answer), PRACTICE, {}, more_steps={"rare_step"})
    assert r["connected"] == ["t_decide", "rare_step"]


def test_an_input_that_looks_fixed_only_because_of_a_filler_still_counts_as_changing():
    def answer(request):
        needs = t_needs(request)  # no labels: a filler with players=None on every request
        if not t_recheck(Ping(n=needs.players or 0)).ok:
            return Answer(pick=None, explanation="no")
        return Answer(pick="A", explanation="yes")
    r = connected.check(system(answer), PRACTICE, {})
    assert r["same_input"] == {} and r["connected"] == ["t_needs", "t_recheck"]


def test_a_step_called_the_same_way_several_times_on_every_request_has_the_same_input():
    def answer(request):
        choice = t_decide(request)
        for n in range(3):
            if not t_recheck(Ping(n=n)).ok:
                return Answer(pick=None, explanation="no")
        return answer_of(choice)
    r = connected.check(system(answer), PRACTICE, {})
    assert r["same_input"] == {"t_recheck": 10} and r["connected"] == ["t_decide"]


def test_a_step_we_couldnt_finish_testing_counts_as_connected():
    def answer(request):
        choice = t_decide(request)
        t_recheck(Ping(n=len(request.request)))
        return answer_of(choice)
    r = connected.check(system(answer), PRACTICE, {}, seconds=0)
    assert r["unused"] == [] and r["connected"] == ["t_decide", "t_recheck"]
