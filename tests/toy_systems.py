"""Small systems for the tests. They are not examples of good designs, and not how to lay out your own system.

Your system is a file like systems/compound.py: top-level functions, with @step on each step. This file holds several
tiny systems at once, so each one is a class used only as a container (it is never instantiated). A function written
inside a class normally expects `self`; @staticmethod makes it a plain function stored in the class, so a call like
compound_ok.shortlist(request) works. So the steps here have both decorators (@staticmethod on top, then @step), and
`answer`, which is the system's entry point and not a step, has only @staticmethod.
"""
from pydantic import BaseModel

from p1 import Answer, Request, call, call_json, step


class Letters(BaseModel):
    letters: list[str]


class Verdict(BaseModel):
    letter: str
    fits: bool


class compound_ok:
    VARIANT = "compound"

    @staticmethod
    @step
    def shortlist(request: Request) -> Letters:
        return Letters(letters=[c.id for c in request.candidates])

    @staticmethod
    @step
    def judge(v: Verdict) -> Verdict:
        return call_json(f"judge {v.letter}", Verdict)

    @staticmethod
    def answer(request: Request) -> Answer:
        short = compound_ok.shortlist(request)
        verdicts = [compound_ok.judge(Verdict(letter=l, fits=False)) for l in short.letters[:3]]
        fits = [v.letter for v in verdicts if v.fits]
        return Answer(pick=fits[0] if fits else None, explanation="toy")


class single_two_calls:
    VARIANT = "single"

    @staticmethod
    def answer(request: Request) -> Answer:
        call("one")
        call("two")
        return Answer(pick=None, explanation="never reached")


class compound_call_outside_step:
    VARIANT = "compound"

    @staticmethod
    def answer(request: Request) -> Answer:
        call("no step")
        return Answer(pick=None, explanation="never reached")


class compound_bad_output:
    VARIANT = "compound"

    @staticmethod
    @step(name="broken")
    def broken(request: Request) -> Verdict:
        return {"letter": "A"}  # missing "fits"

    @staticmethod
    def answer(request: Request) -> Answer:
        compound_bad_output.broken(request)
        return Answer(pick=None, explanation="never reached")


class Ping(BaseModel):
    n: int


class compound_ten_calls:
    """10 model calls for each request, the most a compound system may make."""
    VARIANT = "compound"

    @staticmethod
    @step(name="ping")
    def ping(p: Ping) -> Ping:
        call(f"ping {p.n}")
        return p

    @staticmethod
    def answer(request: Request) -> Answer:
        for n in range(10):
            compound_ten_calls.ping(Ping(n=n))
        return Answer(pick=None, explanation="toy")


class compound_eleven_calls:
    """11 model calls for each request, one past the limit."""
    VARIANT = "compound"

    @staticmethod
    def answer(request: Request) -> Answer:
        for n in range(11):
            compound_ten_calls.ping(Ping(n=n))
        return Answer(pick=None, explanation="never reached")
