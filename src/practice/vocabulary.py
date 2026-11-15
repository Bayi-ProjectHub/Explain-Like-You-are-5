"""共享中英术语条目；抽题只返回研究提示，不提前泄露参考答案。"""

from __future__ import annotations

import json
import random
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Language = Literal["zh", "en"]
Difficulty = Literal["starter", "intermediate", "advanced"]


class LocalizedText(BaseModel):
    zh: str = Field(min_length=1)
    en: str = Field(min_length=1)


class Term(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: str
    difficulty: Difficulty
    title: LocalizedText
    prompt: LocalizedText
    preparation_seconds: int = Field(gt=0)
    speaking_seconds: int = Field(gt=0)


class Vocabulary(BaseModel):
    version: int
    categories: dict[str, LocalizedText]
    terms: list[Term]

    @model_validator(mode="after")
    def validate_terms(self) -> Vocabulary:
        ids = [term.id for term in self.terms]
        if len(ids) != len(set(ids)):
            raise ValueError("词库中存在重复 id")
        if any(term.category not in self.categories for term in self.terms):
            raise ValueError("术语引用了不存在的分类")
        return self


@lru_cache(maxsize=1)
def load_vocabulary() -> Vocabulary:
    path = Path(__file__).with_name("vocabulary.json")
    return Vocabulary.model_validate(json.loads(path.read_text(encoding="utf-8")))


def find_term(term_id: str) -> Term | None:
    return next((term for term in load_vocabulary().terms if term.id == term_id), None)


def filter_terms(category: str | None, difficulty: Difficulty | None) -> list[Term]:
    return [
        term for term in load_vocabulary().terms
        if (category is None or term.category == category)
        and (difficulty is None or term.difficulty == difficulty)
    ]


def draw_term(category: str | None, difficulty: Difficulty | None, exclude_id: str | None) -> Term | None:
    terms = filter_terms(category, difficulty)
    alternatives = [term for term in terms if term.id != exclude_id]
    return random.choice(alternatives or terms) if terms else None
