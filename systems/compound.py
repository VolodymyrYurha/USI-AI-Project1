"""The compound variant: one small, simple question at a time.

How a request is answered (every box is a declared @step):

    request text
        |
        v
    extract_requirements   MODEL  reads the request, fills in a checklist (players, minutes, complexity, ...)
        |
        v   for each of the five candidate games:
    check_card             CODE   settles everything that is a number or a tag on the card
        |   (a game the card already rules out is not sent to the model)
        v
    rate_description      MODEL  reads ONE game's description and rates the game: good, mixed, poor or not mentioned
        |
        v
    choose_game            CODE   returns the first game rated good, else the first rated mixed, else declines

Model calls per request: 1 (+1 retry) to extract the requirements, plus at most 5 to judge descriptions.
That is at most 7, under the limit of 10.
"""

import re
from typing import Callable, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

from p1 import Answer, Request, call, parse_json, step
from p1.types import Candidate

VARIANT = "compound"

MAX_DESCRIPTION_CHARS = 1500  # how much of a game's description the judge reads


def ask_model(prompt: str, output_type: type[BaseModel]):
    """Call the model once and parse its reply into `output_type`.
    The model sometimes writes the string "null"; it is read as the JSON value null."""
    return parse_json(call(prompt).replace('"null"', "null"), output_type)


# =====================================================================================================
# Step 1 (model): the request text -> a checklist of what the person requires
# =====================================================================================================


class PersonRequest(BaseModel):
    """Input of step 1: only what the person wrote, without the candidate games."""

    text: str


class Requirements(BaseModel):
    """The checklist. Every field has a default, so a reply that leaves one out still fits the contract."""

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


REQUIREMENTS_PROMPT = """Read the request and fill in a checklist of the requirements it STATES. Ignore wishes ("would be nice", "would be amazing", "we'd love") and ignore anything not stated.
- players: everyone who will play, including the writer. "me and my brother" = 2; "my wife and I" = 2; "me and my three friends" = 4; "five of us" = 5; "game night with six friends" = 7. null if not stated.
- max_minutes: "an hour", "an hour tops", "about an hour" = 60; "half an hour" = 30; "two hours" = 120; null if not stated.
- complexity: "easy rules", "simple", "beginners", "never play board games", "casual" = "light". "deep strategy", "meaty", "nothing light" = "heavy". "not too simple, not too heavy" or "a step up from mainstream games" = "medium". Otherwise "none".
- coop: "together against the game", "team up against the game", "as one team" = "cooperative". "head to head", "against each other" = "competitive". Otherwise "none".
- min_age: the child's age if a child will play ("our 8-year-old" = 8), else null.
- no_fighting: true for "no fighting", "no combat". no_violence: true for "nothing violent". no_horror: true for "nothing scary", "nothing creepy". no_timer: true for "no timers", "no racing against the clock". no_elimination: true for "nobody knocked out", "nobody sitting out".

Answer with JSON only, with exactly these keys:
{"players": 4, "max_minutes": 60, "complexity": "light", "coop": "none", "min_age": null, "no_fighting": false, "no_violence": false, "no_horror": false, "no_timer": false, "no_elimination": false}
The values above are only an example of the format. Use null without quotes for a missing number.

Request:
"""


@step
def extract_requirements(person: PersonRequest) -> Requirements:
    prompt = REQUIREMENTS_PROMPT + person.text.strip()
    for _attempt in range(
        2
    ):  # one retry if the reply does not fit the Requirements type
        try:
            return ask_model(prompt, Requirements)
        except ValidationError:
            continue
    return Requirements()  # nothing could be read: no requirements


# =====================================================================================================
# Step 2 (code): check one candidate's card. Numbers and tags only, no model.
# =====================================================================================================


class CardCheckInput(BaseModel):
    requirements: Requirements
    candidate: Candidate


class CardCheck(BaseModel):
    """What the card says about one candidate."""

    candidate_id: str
    failure: Optional[str] = Field(
        None, description="Why the card rules this game out; null if it does not"
    )
    passed: list[str] = Field(
        default_factory=list, description="Requirements the card already confirms"
    )
    to_read: list[str] = Field(
        default_factory=list, description="Requirements only the description can settle"
    )


# ---- reading a number out of a description, for fields the card leaves empty


def described_players(text: str) -> Optional[tuple[int, int]]:
    """The player range a description states: "2 to 4 players", "up to 5 players", "for 2 players"."""
    ranged = re.search(
        r"(\d+)\s*(?:to|-|–|—)\s*(\d+)[\s-]*(?:players?|people|persons)", text, re.I
    )
    if ranged:
        return int(ranged.group(1)), int(ranged.group(2))
    up_to = re.search(r"up to (\d+)[\s-]*(?:players?|people|persons)", text, re.I)
    if up_to:
        return 1, int(up_to.group(1))
    exact = re.search(r"(\d+)[\s-]*players?\b", text, re.I)
    if exact:
        return int(exact.group(1)), int(exact.group(1))
    return None


def described_minutes(text: str) -> Optional[int]:
    """The longest play time a description states. Times to learn or explain the rules are skipped."""
    times = []
    for match in re.finditer(r"(\d+)\s*(?:minutes?|mins?)\b", text, re.I):
        words_before = text[max(0, match.start() - 40) : match.start()]
        if not re.search(r"learn|teach|explain|setup|set up", words_before, re.I):
            times.append(int(match.group(1)))
    return max(times) if times else None


def described_min_age(text: str) -> Optional[int]:
    found = re.search(
        r"ages?\s*(\d+)\s*(?:\+|and up|and older|or older|plus)", text, re.I
    ) or re.search(r"(\d+)\s*\+", text)
    return int(found.group(1)) if found else None


# ---- one function per kind of requirement. Each returns the reason the game fails, or None.
# ---- A check that passes records what it confirmed in `result.passed`; a point only the description can settle
# ---- goes in `result.to_read`.


def check_players(
    req: Requirements, game: Candidate, result: CardCheck
) -> Optional[str]:
    if req.players is None:
        return None
    if game.card.players:
        low, high = game.card.players[0], game.card.players[-1]
        if not low <= req.players <= high:
            return f"Players: the card says {low} to {high}, which does not include {req.players}."
        result.passed.append(
            f"{req.players} players fit the card's range {low} to {high}."
        )
        return None
    # The card lists no players: the description must state it, and then the numbers decide.
    stated = described_players(game.description)
    if stated is None:
        return "The card lists no player count and the description states none."
    low, high = stated
    if not low <= req.players <= high:
        return f"Players: the description says {low} to {high}, not {req.players}."
    result.passed.append(
        f"{req.players} players fit the description's {low} to {high}."
    )
    return None


def check_play_time(
    req: Requirements, game: Candidate, result: CardCheck
) -> Optional[str]:
    if req.max_minutes is None:
        return None
    if game.card.minutes:
        longest = game.card.minutes[-1]
        if longest > req.max_minutes:
            return f"Play time: the longest time is {longest} minutes, over the limit of {req.max_minutes}."
        result.passed.append(
            f"Longest play time {longest} minutes is within {req.max_minutes}."
        )
        return None
    stated = described_minutes(game.description)
    if stated is None:
        return "The card lists no play time and the description states none."
    if stated > req.max_minutes:
        return f"Play time: the description says {stated} minutes, over the limit of {req.max_minutes}."
    result.passed.append(
        f"The described play time of {stated} minutes is within {req.max_minutes}."
    )
    return None


def check_min_age(
    req: Requirements, game: Candidate, result: CardCheck
) -> Optional[str]:
    if req.min_age is None:
        return None
    if game.card.age is not None:
        if game.card.age > req.min_age:
            return f"Age: the minimum age is {game.card.age}, above {req.min_age}."
        result.passed.append(f"Minimum age {game.card.age} is at most {req.min_age}.")
        return None
    stated = described_min_age(game.description)
    if stated is None:
        return "The card lists no minimum age and the description states none."
    if stated > req.min_age:
        return f"Age: the description says {stated}+, above {req.min_age}."
    result.passed.append(
        f"The described minimum age {stated} is at most {req.min_age}."
    )
    return None


def check_cooperation(
    req: Requirements, game: Candidate, result: CardCheck
) -> Optional[str]:
    is_cooperative = "Cooperative Game" in game.card.mechanics
    if req.coop == "cooperative":
        if not is_cooperative:
            return "It is not cooperative (no Cooperative Game mechanic)."
        result.passed.append("It is cooperative.")
    if req.coop == "competitive":
        if is_cooperative:
            return "It is cooperative, not competitive."
        result.passed.append("It is competitive.")
    return None


# requirement flag -> (what to call it, does the card carry the tag?)
AVOID_FEATURES: dict[str, tuple[str, Callable[[set, set], bool]]] = {
    "no_fighting": ("fighting", lambda cats, mech: "Fighting" in cats),
    "no_violence": (
        "violence",
        lambda cats, mech: bool(cats & {"Wargame", "Fighting"}),
    ),
    "no_horror": ("horror", lambda cats, mech: bool(cats & {"Horror", "Zombies"})),
    "no_timer": (
        "a timer",
        lambda cats, mech: "Real-time" in cats or "Real-Time" in mech,
    ),
    "no_elimination": (
        "player elimination",
        lambda cats, mech: "Player Elimination" in mech,
    ),
}


def check_avoided_features(
    req: Requirements, game: Candidate, result: CardCheck
) -> Optional[str]:
    """A tag on the card always counts. Without the tag, only the description can tell, so the model reads it."""
    categories, mechanics = set(game.card.categories), set(game.card.mechanics)
    for flag, (label, card_has_tag) in AVOID_FEATURES.items():
        if getattr(req, flag):
            if card_has_tag(categories, mechanics):
                return f"Its card has the tag for {label}."
            result.to_read.append(flag)
    return None


# ---- complexity, from BoardGameGeek's weight (1 to 5) and the game types

STRATEGY_STYLE_TYPES = {"strategy", "thematic", "war", "abstract"}


def is_light(weight: float, types: set) -> bool:
    return (
        weight <= 1.3
        or bool(types & {"party", "children's"})
        or ("family" in types and weight < 2.0)
    )


def is_not_light(weight: float, types: set) -> bool:
    return weight >= 4.0 or (
        bool(types) and types <= STRATEGY_STYLE_TYPES and weight >= 2.5
    )


def is_heavy(weight: float, types: set) -> bool:
    return weight >= 4.0 or (
        bool(types & {"strategy", "war"}) and "family" not in types and weight >= 3.5
    )


def is_not_heavy(weight: float, types: set) -> bool:
    return weight <= 1.3 or bool(types & {"party", "children's", "family"})


def check_complexity(
    req: Requirements, game: Candidate, result: CardCheck
) -> Optional[str]:
    if req.complexity == "none":
        return None
    if game.card.complexity is None:
        if req.complexity == "medium":
            return "Its complexity is not listed, so medium cannot be checked."
        result.to_read.append(
            req.complexity
        )  # only the description can decide light or heavy
        return None

    weight = game.card.complexity.weight
    types = set(game.card.types)
    light, heavy = is_light(weight, types), is_heavy(weight, types)

    if req.complexity == "light":
        if light:
            result.passed.append(f"Complexity: light (weight {weight:.2f}).")
        elif is_not_light(weight, types):
            return f"Complexity: not light (weight {weight:.2f})."
        else:
            result.to_read.append("light")
    elif req.complexity == "heavy":
        if heavy:
            result.passed.append(f"Complexity: heavy (weight {weight:.2f}).")
        elif is_not_heavy(weight, types):
            return f"Complexity: not heavy (weight {weight:.2f})."
        else:
            result.to_read.append("heavy")
    else:  # medium: neither light nor heavy, and a weight between 2.0 and 3.5
        if light or heavy:
            return f"Complexity: {'light' if light else 'heavy'}, not medium (weight {weight:.2f})."
        if not 2.0 <= weight <= 3.5:
            return f"Complexity: weight {weight:.2f} is outside the medium range."
        result.passed.append(f"Complexity: the card says medium (weight {weight:.2f}).")
        # The description is not sent to the model for this point. On 50 requests all 8 games with only this
        # point open were acceptable, and the model failed 4 of them by guessing "complex rules" from a theme.
        # To bring the check back, add: result.to_read.append("medium")
    return None


CARD_CHECKS = (
    check_players,
    check_play_time,
    check_min_age,
    check_cooperation,
    check_avoided_features,
    check_complexity,
)


@step
def check_card(inp: CardCheckInput) -> CardCheck:
    """Run the card checks in order and stop at the first one that rules the game out."""
    result = CardCheck(candidate_id=inp.candidate.id)
    for check in CARD_CHECKS:
        failure = check(inp.requirements, inp.candidate, result)
        if failure:
            result.failure = failure
            break
    return result


# =====================================================================================================
# Step 3 (model): read ONE game's description and answer the points the card could not settle
# =====================================================================================================


class Verdict(BaseModel):
    """The same format for every judge call: how well ONE game fits, in one of four words."""

    rating: Literal["good", "mixed", "poor", "not mentioned"] = Field(
        description="good: every point confirmed. mixed: nothing fails, but a point is only implied. "
        "poor: a point clearly fails. not mentioned: the description says nothing about a point."
    )
    explanation: str

    @field_validator("rating", mode="before")
    @classmethod
    def tidy_rating(cls, value):
        """Accept 'Good', 'not_mentioned', ' Poor ' and so on."""
        return value.strip().lower().replace("_", " ") if isinstance(value, str) else value


class DescriptionCheckInput(BaseModel):
    requirements: Requirements
    request_text: str = Field(
        "", description="The person's own words, for details the checklist could not capture"
    )
    candidate: Candidate
    passed: list[str] = Field(
        default_factory=list, description="What the code already confirmed on the card"
    )
    to_read: list[str] = Field(
        default_factory=list, description="Points left to settle from the description"
    )


# One question per point. The key is what check_card puts into `to_read`.
DESCRIPTION_QUESTIONS = {
    "light": 'Easy rules are needed. Does the description explicitly say the rules are easy or simple (for example "easy to learn", "simple rules"), or call it a light game? If it does not say so, or it says the rules are complex or for experienced players, the game fails.',
    "heavy": 'A heavy game is needed. Does the description explicitly say the RULES are complex or the game is for experienced players? If it does not say so, the game fails. "Deep strategy" or hidden roles alone do not count.',
    "medium": 'The card already says this game\'s complexity is medium, so the game MEETS the request unless you find a fail. It fails ONLY if the description contains a sentence that directly says the rules are easy or simple (for example "easy to learn", "simple rules") or directly says the rules are complex or for experienced players. Do NOT fail it for a list of components or mechanics, a war or strategy theme, or because the game sounds complicated: a game that is not simple is exactly what the request wants.',
    "no_fighting": "Do players' characters or creatures attack, battle or duel other characters or creatures as something players do? If yes, it fails. Armies on a map, raiding, figures of speech, a heist, and a penalty called an attack do not count.",
    "no_violence": "Is the game clearly about war, raiding, conquest, battles or killing? If yes, it fails. Conflict, rivalry, revenge, villains, a heist or catching a crook, and a grim backstory do not count.",
    "no_horror": "Does the description present horror creatures, hauntings, being hunted or gore as frightening? If yes, it fails. Generic fantasy monsters, cartoon spookiness and murder mysteries do not count.",
    "no_timer": 'Does play mean racing a clock or sand timer, or everyone playing at once as fast as they can? If yes, it fails. A countdown track or the word "fast-paced" does not count.',
    "no_elimination": "Can a player be knocked out and have to sit and watch for the rest of a game or a round? If yes, it fails. Losing points or cards while still playing does not count.",
}

VERDICT_FORMAT = """Answer with JSON only, with exactly these keys:
{"rating": "<good, mixed, not mentioned or poor>", "explanation": "<one or two sentences>"}
rating is exactly one of these four, judged from the numbered points above:
- good: every point is satisfied. A point that asks whether a problem is present (fighting, violence, horror, a timer, a player knocked out) is satisfied when the description does not show that problem. Saying nothing about it is fine.
- mixed: nothing clearly fails and nothing needed is missing, but at least one point is only implied or suggested
- not mentioned: a point needs something to be stated (a number of players, a play time, an age, easy or complex rules) and the description does not state it
- poor: at least one point clearly fails, because the description directly shows the problem. A suggestion or an impression is not enough for poor.
If several apply, use the worst one, in this order: poor, not mentioned, mixed, good."""

REQUEST_BLOCK = """The person's own words:
"{text}"
This is the one exception to judging only the numbered points: use these words to catch a detail the numbered points do not cover. Wishes ("would be nice", "would be amazing", "we'd love") are not requirements and never lower the rating. If the description clearly goes against something the person asked for that the numbered points do not cover, rate the game mixed. This can lower good to mixed, but on its own it never makes a game poor or not mentioned.

"""

JUDGE_PROMPT = """Decide whether this ONE board game meets a request. The card was already checked by the code, and these points PASS, so do not check them again:
{passed}

Read the description for these points. Say the game fails only if the description clearly shows it fails a point; where a point asks for something to be stated, the game fails if it is not stated:
{questions}

Judge ONLY the numbered points above. Anything else in the description (a theme, war, violence, horror, how complicated the game sounds) is not a requirement, so it must not lower the rating. If no point fails, the game meets the request. Use only the description, never outside knowledge.

{request_block}{answer_format}

Game:
{game}"""


def describe_game(game: Candidate) -> str:
    year = f" ({game.year})" if game.year else ""
    description = game.description.strip()
    if len(description) > MAX_DESCRIPTION_CHARS:
        description = description[:MAX_DESCRIPTION_CHARS] + "..."
    return (
        f"[{game.id}] {game.name}{year}\n"
        f"Categories: {', '.join(game.card.categories) or 'none'}\n"
        f"Mechanics: {', '.join(game.card.mechanics) or 'none'}\n"
        f"Description:\n{description}"
    )


def build_judge_prompt(inp: DescriptionCheckInput) -> str:
    passed = (
        "\n".join(f"- {fact}" for fact in inp.passed)
        or "- (nothing to check on the card)"
    )
    questions = (
        "\n".join(
            f"{number}. {DESCRIPTION_QUESTIONS[point]}"
            for number, point in enumerate(inp.to_read, 1)
        )
        or "(nothing)"
    )
    return JUDGE_PROMPT.format(
        passed=passed,
        questions=questions,
        request_block=REQUEST_BLOCK.format(text=inp.request_text.strip())
        if inp.request_text.strip()
        else "",
        answer_format=VERDICT_FORMAT,
        game=describe_game(inp.candidate),
    )


@step
def rate_description(inp: DescriptionCheckInput) -> Verdict:
    try:
        return ask_model(build_judge_prompt(inp), Verdict)
    except ValidationError:
        # No retry: the calls for the requirements and the five judges already use most of the limit.
        return Verdict(rating="poor", explanation="The model's reply could not be read.")


# =====================================================================================================
# Step 4 (code): choose the game
# =====================================================================================================


class CandidateVerdict(BaseModel):
    candidate_id: str
    verdict: Verdict


class AllVerdicts(BaseModel):
    candidates: list[CandidateVerdict]


# best first. A game rated "poor" or "not mentioned" is never recommended.
RATING_ORDER = {"good": 0, "mixed": 1, "not mentioned": 2, "poor": 3}


@step
def choose_game(all_verdicts: AllVerdicts) -> Answer:
    """Return the first game rated good; if there is none, the first rated mixed; otherwise decline."""
    best = min(all_verdicts.candidates, key=lambda item: RATING_ORDER[item.verdict.rating])  # first one on a tie
    if best.verdict.rating in ("good", "mixed"):
        return Answer(pick=best.candidate_id, explanation=f"{best.verdict.rating}: {best.verdict.explanation}")
    return Answer(pick=None, explanation=f"No game is a good or mixed fit. {best.verdict.explanation}")


# =====================================================================================================
# The system: wire the steps together
# =====================================================================================================


def answer(request: Request) -> Answer:
    requirements = extract_requirements(PersonRequest(text=request.request))

    verdicts = []
    for game in request.candidates:
        card = check_card(CardCheckInput(requirements=requirements, candidate=game))
        if card.failure:  # the card alone rules the game out: no model call
            verdict = Verdict(rating="poor", explanation=card.failure)
        elif not card.to_read:  # the card confirms everything: nothing left for the model to read
            verdict = Verdict(rating="good", explanation=" ".join(card.passed) or "No requirement to check.")
        else:
            verdict = rate_description(
                DescriptionCheckInput(
                    requirements=requirements,
                    request_text=request.request,
                    candidate=game,
                    passed=card.passed,
                    to_read=card.to_read,
                )
            )
        verdicts.append(CandidateVerdict(candidate_id=game.id, verdict=verdict))

    return choose_game(AllVerdicts(candidates=verdicts))
