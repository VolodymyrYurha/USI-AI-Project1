"""The compound variant: one small call per candidate.

1. extract_needs (model, 1 call): the request text -> a short checklist of requirements.
2. judge (model, 1 call per candidate): the checklist + ONE candidate -> {pick, percentage, explanation}.
3. Plain Python: among the candidates the judge says meet everything, return the one with the highest percentage;
   decline if none does.

At most 1 (+1 retry) + 5 = 7 model calls per request, under the limit of 10.
"""

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from p1 import Answer, Request, call, parse_json, step
from p1.render import render_card
from p1.types import Candidate

VARIANT = "compound"

MAX_DESCRIPTION = 1500  # characters of a game's description that the judge sees


class RequestText(BaseModel):
    text: str


class Needs(BaseModel):
    """The requirements the request states. Every field has a default, so a reply that leaves one out still fits."""

    players: Optional[int] = Field(
        None,
        description="How many people play, counting the writer; null if not stated",
    )
    max_minutes: Optional[int] = Field(
        None, description="Longest play time in minutes; null if not stated"
    )
    complexity: Literal["light", "medium", "heavy", "none"] = "none"
    coop: Literal["cooperative", "competitive", "none"] = "none"
    min_age: Optional[int] = Field(
        None, description="The child's age if a child will play; null if not stated"
    )
    no_fighting: bool = False
    no_violence: bool = False
    no_horror: bool = False
    no_timer: bool = False
    no_elimination: bool = False


NEEDS_INSTRUCTIONS = """Read the request and fill in a checklist of the requirements it STATES. Ignore wishes ("would be nice", "would be amazing", "we'd love") and ignore anything not stated.
- players: everyone who will play, including the writer. "me and my brother" = 2; "my wife and I" = 2; "me and my three friends" = 4; "five of us" = 5; "game night with six friends" = 7. null if not stated.
- max_minutes: "an hour", "an hour tops", "about an hour" = 60; "half an hour" = 30; "two hours" = 120; null if not stated.
- complexity: "easy rules", "simple", "beginners", "never play board games", "casual" = "light". "deep strategy", "meaty", "nothing light" = "heavy". "not too simple, not too heavy" or "a step up from mainstream games" = "medium". Otherwise "none".
- coop: "together against the game", "team up against the game", "as one team" = "cooperative". "head to head", "against each other" = "competitive". Otherwise "none".
- min_age: the child's age if a child will play ("our 8-year-old" = 8), else null.
- no_fighting: true for "no fighting", "no combat". no_violence: true for "nothing violent". no_horror: true for "nothing scary", "nothing creepy". no_timer: true for "no timers", "no racing against the clock". no_elimination: true for "nobody knocked out", "nobody sitting out".

Answer with JSON only, with exactly these keys:
{"players": 4, "max_minutes": 60, "complexity": "light", "coop": "none", "min_age": null, "no_fighting": false, "no_violence": false, "no_horror": false, "no_timer": false, "no_elimination": false}
The values above are only an example of the format. Use null without quotes for a missing number."""


def _ask(prompt: str, model: type[BaseModel]):
    """One model call, parsed into `model`. A quoted "null" is read as null, which the model sometimes writes."""
    return parse_json(call(prompt).replace('"null"', "null"), model)


@step
def extract_needs(req: RequestText) -> Needs:
    prompt = f"{NEEDS_INSTRUCTIONS}\n\nRequest:\n{req.text.strip()}"
    for _ in range(2):  # one retry if the reply doesn't fit
        try:
            return _ask(prompt, Needs)
        except ValidationError:
            continue
    return Needs()


class Verdict(BaseModel):
    """The same format for every judge call. `pick` is this candidate's letter if it meets every requirement, else
    null. `percentage` is how sure you are that it meets every requirement."""

    pick: Optional[Literal["A", "B", "C", "D", "E"]] = Field(
        description="This candidate's letter if it meets every requirement, else null"
    )
    percentage: int = Field(
        ge=0, le=100, description="How sure that it meets every requirement, 0 to 100"
    )
    explanation: str


class JudgeInput(BaseModel):
    needs: Needs
    candidate: Candidate
    done: list[str] = Field(
        default_factory=list
    )  # what the code already checked on the card, all passing
    todo: list[str] = Field(
        default_factory=list
    )  # what is left to read in the description


STRATEGYISH = {"strategy", "thematic", "war", "abstract"}


def _described_players(text: str) -> Optional[tuple[int, int]]:
    """The player range a description states, e.g. "2 to 4 players", "up to 5 players", "for 2 players"."""
    m = re.search(r"(\d+)\s*(?:to|-|\u2013|\u2014)\s*(\d+)[\s-]*(?:players?|people|persons)", text, re.I)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"up to (\d+)[\s-]*(?:players?|people|persons)", text, re.I)
    if m:
        return 1, int(m.group(1))
    m = re.search(r"(\d+)[\s-]*players?\b", text, re.I)
    if m:
        return int(m.group(1)), int(m.group(1))
    return None


def _described_minutes(text: str) -> Optional[int]:
    """The longest play time a description states in minutes. Times to learn or explain the rules are skipped."""
    found = []
    for m in re.finditer(r"(\d+)\s*(?:minutes?|mins?)\b", text, re.I):
        if not re.search(r"learn|teach|explain|setup|set up", text[max(0, m.start() - 40):m.start()], re.I):
            found.append(int(m.group(1)))
    return max(found) if found else None


def _described_age(text: str) -> Optional[int]:
    m = re.search(r"ages?\s*(\d+)\s*(?:\+|and up|and older|or older|plus)", text, re.I) or re.search(r"(\d+)\s*\+", text)
    return int(m.group(1)) if m else None


def _card_checks(n: Needs, c: Candidate) -> tuple[Optional[str], list[str], list[str]]:
    """The checks that are only numbers and tags, done in Python. Returns (reason it fails or None, passed facts,
    keys of what the model must still read in the description)."""
    card = c.card
    w = card.complexity.weight if card.complexity else None
    types, cats, mech = set(card.types), set(card.categories), set(card.mechanics)
    done: list[str] = []
    todo: list[str] = []

    if n.players is not None:
        if card.players:
            lo, hi = card.players[0], card.players[-1]
            if not lo <= n.players <= hi:
                return (
                    f"Players: the card says {lo} to {hi}, which does not include {n.players}.",
                    done,
                    todo,
                )
            done.append(f"{n.players} players fit the card's range {lo} to {hi}.")
        else:  # not on the card: the description must state it, and then the numbers decide
            stated = _described_players(c.description)
            if stated is None:
                return "The card lists no player count and the description states none.", done, todo
            if not stated[0] <= n.players <= stated[1]:
                return f"Players: the description says {stated[0]} to {stated[1]}, not {n.players}.", done, todo
            done.append(f"{n.players} players fit the description's {stated[0]} to {stated[1]}.")
    if n.max_minutes is not None:
        if card.minutes:
            hi = card.minutes[-1]
            if hi > n.max_minutes:
                return (
                    f"Play time: the longest time is {hi} minutes, over the limit of {n.max_minutes}.",
                    done,
                    todo,
                )
            done.append(f"Longest play time {hi} minutes is within {n.max_minutes}.")
        else:
            stated = _described_minutes(c.description)
            if stated is None:
                return "The card lists no play time and the description states none.", done, todo
            if stated > n.max_minutes:
                return f"Play time: the description says {stated} minutes, over the limit of {n.max_minutes}.", done, todo
            done.append(f"The described play time of {stated} minutes is within {n.max_minutes}.")
    if n.min_age is not None:
        if card.age is not None:
            if card.age > n.min_age:
                return (
                    f"Age: the minimum age is {card.age}, above {n.min_age}.",
                    done,
                    todo,
                )
            done.append(f"Minimum age {card.age} is at most {n.min_age}.")
        else:
            stated = _described_age(c.description)
            if stated is None:
                return "The card lists no minimum age and the description states none.", done, todo
            if stated > n.min_age:
                return f"Age: the description says {stated}+, above {n.min_age}.", done, todo
            done.append(f"The described minimum age {stated} is at most {n.min_age}.")
    if n.coop == "cooperative":
        if "Cooperative Game" not in mech:
            return "It is not cooperative (no Cooperative Game mechanic).", done, todo
        done.append("It is cooperative.")
    if n.coop == "competitive":
        if "Cooperative Game" in mech:
            return "It is cooperative, not competitive.", done, todo
        done.append("It is competitive.")

    for flag, tag_hit, label in (
        ("no_fighting", "Fighting" in cats, "fighting"),
        ("no_violence", bool(cats & {"Wargame", "Fighting"}), "violence"),
        ("no_horror", bool(cats & {"Horror", "Zombies"}), "horror"),
        ("no_timer", "Real-time" in cats or "Real-Time" in mech, "a timer"),
        ("no_elimination", "Player Elimination" in mech, "player elimination"),
    ):
        if getattr(n, flag):
            if tag_hit:
                return f"Its card has the tag for {label}.", done, todo
            todo.append(flag)

    if n.complexity != "none":
        if w is None:
            if n.complexity == "medium":
                return (
                    "Its complexity is not listed, so medium cannot be checked.",
                    done,
                    todo,
                )
            todo.append(n.complexity)
        else:
            light = (
                w <= 1.3
                or bool(types & {"party", "children's"})
                or ("family" in types and w < 2.0)
            )
            not_light = w >= 4.0 or (bool(types) and types <= STRATEGYISH and w >= 2.5)
            heavy = w >= 4.0 or (
                bool(types & {"strategy", "war"}) and "family" not in types and w >= 3.5
            )
            not_heavy = w <= 1.3 or bool(types & {"party", "children's", "family"})
            if n.complexity == "light":
                if light:
                    done.append(f"Complexity: light (weight {w:.2f}).")
                elif not_light:
                    return f"Complexity: not light (weight {w:.2f}).", done, todo
                else:
                    todo.append("light")
            elif n.complexity == "heavy":
                if heavy:
                    done.append(f"Complexity: heavy (weight {w:.2f}).")
                elif not_heavy:
                    return f"Complexity: not heavy (weight {w:.2f}).", done, todo
                else:
                    todo.append("heavy")
            else:  # medium
                if light or heavy:
                    return (
                        f"Complexity: {'light' if light else 'heavy'}, not medium (weight {w:.2f}).",
                        done,
                        todo,
                    )
                if not 2.0 <= w <= 3.5:
                    return (
                        f"Complexity: weight {w:.2f} is outside the medium range.",
                        done,
                        todo,
                    )
                done.append(f"Complexity: the card says medium (weight {w:.2f}).")
                todo.append("medium")
    return None, done, todo


READ = {
    "light": "Easy rules are needed. Does the description explicitly say the rules are easy or simple (for example \"easy to learn\", \"simple rules\"), or call it a light game? If it does not say so, or it says the rules are complex or for experienced players, the game fails.",
    "heavy": "A heavy game is needed. Does the description explicitly say the RULES are complex or the game is for experienced players? If it does not say so, the game fails. \"Deep strategy\" or hidden roles alone do not count.",
    "medium": "The card says its complexity is medium. It fails ONLY if the description explicitly says the RULES are easy or simple, or explicitly says the rules are complex or for experienced players. The names of components or mechanics, or one complex part of the game, do not count.",
    "no_fighting": "Do players' characters or creatures attack, battle or duel other characters or creatures as something players do? If yes, it fails. Armies on a map, raiding, figures of speech, a heist, and a penalty called an attack do not count.",
    "no_violence": "Is the game clearly about war, raiding, conquest, battles or killing? If yes, it fails. Conflict, rivalry, revenge, villains, a heist or catching a crook, and a grim backstory do not count.",
    "no_horror": "Does the description present horror creatures, hauntings, being hunted or gore as frightening? If yes, it fails. Generic fantasy monsters, cartoon spookiness and murder mysteries do not count.",
    "no_timer": "Does play mean racing a clock or sand timer, or everyone playing at once as fast as they can? If yes, it fails. A countdown track or the word \"fast-paced\" does not count.",
    "no_elimination": "Can a player be knocked out and have to sit and watch for the rest of a game or a round? If yes, it fails. Losing points or cards while still playing does not count.",
}


JUDGE_FORMAT = """Answer with JSON only, with exactly these keys:
{"pick": "{LETTER}", "percentage": <number 0 to 100>, "explanation": "<one or two sentences>"}
or, if the description makes the game fail:
{"pick": null, "percentage": <number 0 to 100>, "explanation": "<what fails>"}
pick is "{LETTER}" (this game's letter) if the game meets the request, otherwise null (no quotes). percentage is how sure you are that it meets the request, from 0 to 100."""


def _judge_prompt(inp: JudgeInput) -> str:
    c = inp.candidate
    year = f" ({c.year})" if c.year else ""
    description = c.description.strip()
    if len(description) > MAX_DESCRIPTION:
        description = description[:MAX_DESCRIPTION] + "..."
    game = f"[{c.id}] {c.name}{year}\nCategories: {', '.join(c.card.categories) or 'none'}\nMechanics: {', '.join(c.card.mechanics) or 'none'}\nDescription:\n{description}"
    done = "\n".join(f"- {d}" for d in inp.done) or "- (nothing to check on the card)"
    todo = (
        "\n".join(f"{i}. {READ[k]}" for i, k in enumerate(inp.todo, 1)) or "(nothing)"
    )
    return (
        f"Decide whether this ONE board game meets a request. The card was already checked by the code, and these points PASS, so do not check them again:\n{done}\n\n"
        f"Read the description for these points. Say the game fails only if the description clearly shows it fails a point; "
        f"where a point asks for something to be stated, the game fails if it is not stated:\n{todo}\n\n"
        f"If no point fails, the game meets the request. Use only the description, never outside knowledge.\n\n"
        f"{JUDGE_FORMAT.replace('{LETTER}', c.id)}\n\nGame:\n{game}"
    )


@step
def judge(inp: JudgeInput) -> Verdict:
    try:
        return _ask(_judge_prompt(inp), Verdict)
    except ValidationError:
        return Verdict(
            pick=None, percentage=0, explanation="The model's reply could not be read."
        )


# ---------------------------------------------------------------- step 3: pick in plain Python


def answer(request: Request) -> Answer:
    needs = extract_needs(RequestText(text=request.request))
    verdicts: list[tuple[Candidate, Verdict]] = []
    for c in request.candidates:
        reason, done, todo = _card_checks(needs, c)
        if reason is not None:  # the card alone already settles it: no model call
            verdicts.append((c, Verdict(pick=None, percentage=0, explanation=reason)))
        else:
            verdicts.append(
                (c, judge(JudgeInput(needs=needs, candidate=c, done=done, todo=todo)))
            )
    fits = [(c, v) for c, v in verdicts if v.pick is not None]
    if not fits:
        best = max(verdicts, key=lambda cv: cv[1].percentage)[1]
        return Answer(
            pick=None,
            explanation=f"No game meets every requirement. {best.explanation}",
        )
    # the highest percentage wins; max() keeps the first of equal ones
    c, v = max(fits, key=lambda cv: cv[1].percentage)
    return Answer(pick=c.id, explanation=f"{v.percentage}%: {v.explanation}")
