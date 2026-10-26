"""
JobIntel - Recommender configuration: explicit, validated hybrid weights.

Signals (only those the data actually supports):
  skill       share of the job's extracted skills that the user has
  content     TF-IDF cosine similarity, user profile text vs job text
  role        user's preferred role matches the job title / role category
  location    job city is one of the user's preferred locations
  popularity  recency proxy (percentile of posting date). Interaction-based popularity
              is not used: there are too few interactions to justify it.
  behavior    affinity learned from the user's OWN interactions (hybrid only; dropped and the
              remaining weights renormalised while the user has no real interactions)

Work model, salary and experience are deliberately NOT scored: the source supplies none
of them (work model is only set when the posting text says remote/hybrid; otherwise it stays missing).
"""

import math
from dataclasses import dataclass, fields
from typing import Dict

SIGNALS = ("skill", "content", "role", "location", "popularity", "behavior")


@dataclass(frozen=True)
class HybridWeights:
    """Raw, non-negative weights. They need not sum to 1; `normalized()` rescales them."""
    skill: float = 0.35
    content: float = 0.30
    role: float = 0.10
    location: float = 0.06
    popularity: float = 0.05
    behavior: float = 0.10   # only active once the user has real interactions (see recommender.behavior)

    def __post_init__(self):
        for f in fields(self):
            v = getattr(self, f.name)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v < 0:
                raise ValueError(f"weight '{f.name}' must be a finite number >= 0, got {v!r}")
        if sum(self.as_dict().values()) <= 0:
            raise ValueError("at least one weight must be > 0")

    def as_dict(self) -> Dict[str, float]:
        return {f.name: float(getattr(self, f.name)) for f in fields(self)}

    def normalized(self) -> Dict[str, float]:
        total = sum(self.as_dict().values())
        return {k: v / total for k, v in self.as_dict().items()}

    @classmethod
    def from_settings(cls) -> "HybridWeights":
        """Defaults come from backend settings. WEIGHT_PREFERENCE is split 50/30 between role and
        location (the previous 0.5/0.3/0.2 role/location/work-model split minus the unusable work model).
        These are starting values, NOT tuned or claimed optimal; Phase D evaluates them."""
        from backend.app.core.config import settings
        return cls(
            skill=settings.WEIGHT_SKILL,
            content=settings.WEIGHT_CONTENT,
            role=settings.WEIGHT_PREFERENCE * 0.5,
            location=settings.WEIGHT_PREFERENCE * 0.3,
            popularity=settings.WEIGHT_POPULARITY,
            behavior=settings.WEIGHT_BEHAVIOR,
        )

    @classmethod
    def only(cls, signal: str) -> "HybridWeights":
        """Single-signal weights, used by the individual baseline strategies."""
        if signal not in SIGNALS:
            raise ValueError(f"unknown signal {signal!r}; expected one of {SIGNALS}")
        return cls(**{s: (1.0 if s == signal else 0.0) for s in SIGNALS})


STRATEGIES = ("hybrid", "skills", "content", "popularity")


def weights_for_strategy(strategy: str, hybrid: HybridWeights = None) -> HybridWeights:
    if strategy == "hybrid":
        return hybrid or HybridWeights.from_settings()
    mapping = {"skills": "skill", "content": "content", "popularity": "popularity"}
    if strategy not in mapping:
        raise ValueError(f"unknown strategy {strategy!r}; expected one of {STRATEGIES}")
    return HybridWeights.only(mapping[strategy])

