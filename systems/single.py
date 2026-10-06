from p1 import Answer, Request, call_json
from p1.render import render_request

VARIANT = "single"

INSTRUCTIONS = """For the requested json of the game recommendation and 5 options, pick the best one, if nothing matches - decline"""

FORMAT = """Answer with JSON only. the only valid form - {"pick": "<your choice>", "explanation": "<one or two sentences>"}
Pick property can only be A, B, C, D or E.
In case of decline return: {"pick": null, "explanation": "<explain why nothing matches. mandatory>"}"""


def answer(request: Request) -> Answer:
    if not INSTRUCTIONS.strip():
        raise NotImplementedError(
            "Write your instructions in INSTRUCTIONS in systems/single.py first."
        )
    return call_json(f"{INSTRUCTIONS}\n\n{FORMAT}\n\n{render_request(request)}", Answer)
