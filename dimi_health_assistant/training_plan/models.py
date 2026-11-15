from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from typing import Any


@dataclass(frozen=True)
class Exercise:
    name: str
    sets: int
    reps: str
    load_kg: float | None
    load_convention: str = "total_external_load"
    rest_seconds: int = 90
    notes: str = ""
    pair_id: str = ""


@dataclass(frozen=True)
class Workout:
    date: str
    kind: str
    title: str
    warmup: str
    exercises: tuple[Exercise, ...] = ()
    main_set: str = ""
    cooldown: str = ""
    estimated_minutes: int = 0
    completion_criteria: str = "Nur mit kontrollierter Bewegung abschließen; bei Beschwerden oder Verschlechterung stoppen."
    source: str = "template"
    rationale: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["stable_id"] = sha256(f"{self.date}|{self.kind}".encode()).hexdigest()[:20]
        return result
