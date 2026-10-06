"""Plain-text versions of a request and its candidates, for putting into prompts. Use them or write your own."""
from __future__ import annotations

from .types import Candidate, Card, Request

NOT_LISTED = "not listed"


def _range(values, unit: str = "") -> str:
    if not values:
        return NOT_LISTED
    lo, hi = values[0], values[-1]
    text = str(lo) if lo == hi else f"{lo} to {hi}"
    return f"{text} {unit}".strip()


def render_card(card: Card) -> str:
    c = card.complexity
    lines = [
        f"Players: {_range(card.players)}",
        f"Play time: {_range(card.minutes, 'minutes')}",
        f"Minimum age: {card.age if card.age is not None else NOT_LISTED}",
        f"Complexity: {f'{c.weight:.2f} out of 5, from {c.votes} votes' if c else NOT_LISTED}",
        f"Game types: {', '.join(card.types) or NOT_LISTED}",
        f"Categories: {', '.join(card.categories) or NOT_LISTED}",
        f"Mechanics: {', '.join(card.mechanics) or NOT_LISTED}",
    ]
    return "\n".join(lines)


def render_candidate(c: Candidate) -> str:
    year = f" ({c.year})" if c.year else ""
    return f"[{c.id}] {c.name}{year}\n{render_card(c.card)}\nDescription:\n{c.description.strip()}"


def render_request(r: Request) -> str:
    games = "\n\n".join(render_candidate(c) for c in r.candidates)
    return f"Request:\n{r.request.strip()}\n\nCandidate games:\n\n{games}"
