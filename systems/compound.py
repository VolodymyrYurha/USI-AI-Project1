"""The compound variant: your system, built from declared steps.

The rules (the README has the details):
1. Every model call happens inside a step declared with @step.
2. A step takes one pydantic model and returns one pydantic model. You define these types; the declared types are
   the step's contract, and the starter code checks them on every call.
3. At most 10 model calls per request, and no data other than the request and its candidates.
4. `answer` takes a Request and returns an Answer, the same as the single-call variant. Plain Python between steps
   is fine.

The example below shows one step, and its instructions are yours to write. Replace it with your own design:
Milestone 2 needs at least 2 connected model steps. To check, run `python -m p1.contracts systems/compound.py`.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

from p1 import Answer, Request, call_json, step
from p1.render import render_request

VARIANT = "compound"


class Choice(BaseModel):
    """The step's output. You label a step in the course app by its fields that have fixed choices: here `pick`,
    which is a letter or null. Free text such as `explanation` isn't labeled. Give each of your model steps at least
    one such field, e.g. a Literal, a bool or a number."""
    pick: Optional[Literal["A", "B", "C", "D", "E"]] = Field(description="A candidate's letter, or null to decline")
    explanation: str


@step
def decide(request: Request) -> Choice:
    instructions = ""  # your instructions for this step
    if not instructions:
        raise NotImplementedError("Write the instructions for the decide step in systems/compound.py first.")
    prompt = (instructions + "\n\n"
              "Answer with JSON only: {\"pick\": \"<letter or null>\", \"explanation\": \"<one or two sentences>\"}\n\n"
              + render_request(request))
    return call_json(prompt, Choice)


def answer(request: Request) -> Answer:
    choice = decide(request)
    return Answer(pick=choice.pick, explanation=choice.explanation)
