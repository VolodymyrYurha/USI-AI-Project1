"""The fixed edges of every Project 1 system: what goes in, and what comes out.

Both variants, the single-call system and your compound system, take a Request and return an Answer. Don't change
these types: our evaluator and our runs on the hidden requests depend on them.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Complexity(BaseModel):
    model_config = ConfigDict(frozen=True)
    weight: float = Field(description="BoardGameGeek's weight, from 1 (light) to 5 (heavy): an average of player votes")
    votes: int = Field(description="How many players voted on the weight")


class Card(BaseModel):
    """BoardGameGeek's numbers and tags for a game. A field set to None is not listed on the card."""
    model_config = ConfigDict(frozen=True)
    players: Optional[list[int]] = Field(None, description="[min, max] number of players")
    minutes: Optional[list[int]] = Field(None, description="[min, max] play time in minutes")
    age: Optional[int] = Field(None, description="Minimum age")
    complexity: Optional[Complexity] = None
    types: list[str] = Field(default_factory=list, description="BoardGameGeek game types, e.g. family, strategy")
    categories: list[str] = Field(default_factory=list)
    mechanics: list[str] = Field(default_factory=list)


class Candidate(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str = Field(description="The candidate's letter, A to E")
    name: str
    year: Optional[int] = None
    description: str = Field(description="BoardGameGeek's description, word for word")
    card: Card


class Request(BaseModel):
    """One person's request and the five candidate games."""
    model_config = ConfigDict(frozen=True)
    id: str
    request: str = Field(description="What the person wrote")
    candidates: list[Candidate]


class Answer(BaseModel):
    """A system's answer: the letter of one candidate, or None to decline, and an explanation for the person."""
    pick: Optional[str] = Field(description="A candidate's letter (A to E), or null to decline")
    explanation: str = Field(description="Why this game fits, or why none does. Use only facts from the card and the description.")
