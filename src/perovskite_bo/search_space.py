"""Search-space definitions shared by optimization strategies."""

from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Any, Protocol, Sequence


class Parameter(Protocol):
    """A tunable parameter that can be sampled and validated."""

    name: str

    def sample(self, random: Random) -> Any: ...

    def contains(self, value: Any) -> bool: ...


@dataclass(frozen=True)
class FloatParameter:
    name: str
    lower: float
    upper: float

    def __post_init__(self) -> None:
        if self.lower > self.upper:
            raise ValueError(f"{self.name}: lower bound must not exceed upper bound")

    def sample(self, random: Random) -> float:
        return random.uniform(self.lower, self.upper)

    def contains(self, value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and self.lower <= value <= self.upper


@dataclass(frozen=True)
class IntegerParameter:
    name: str
    lower: int
    upper: int

    def __post_init__(self) -> None:
        if self.lower > self.upper:
            raise ValueError(f"{self.name}: lower bound must not exceed upper bound")

    def sample(self, random: Random) -> int:
        return random.randint(self.lower, self.upper)

    def contains(self, value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and self.lower <= value <= self.upper


@dataclass(frozen=True)
class ChoiceParameter:
    name: str
    choices: Sequence[Any]

    def __post_init__(self) -> None:
        if not self.choices:
            raise ValueError(f"{self.name}: at least one choice is required")

    def sample(self, random: Random) -> Any:
        return random.choice(self.choices)

    def contains(self, value: Any) -> bool:
        return value in self.choices


@dataclass(frozen=True)
class SearchSpace:
    """Collection of independently tunable process parameters."""

    parameters: Sequence[Parameter]

    def __post_init__(self) -> None:
        names = [parameter.name for parameter in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError("search-space parameter names must be unique")

    def sample(self, random: Random) -> dict[str, Any]:
        return {parameter.name: parameter.sample(random) for parameter in self.parameters}

    def validate(self, values: dict[str, Any]) -> None:
        expected = {parameter.name for parameter in self.parameters}
        actual = set(values)
        if actual != expected:
            missing = sorted(expected - actual)
            unexpected = sorted(actual - expected)
            raise ValueError(f"search-space keys differ: missing={missing}, unexpected={unexpected}")
        for parameter in self.parameters:
            if not parameter.contains(values[parameter.name]):
                raise ValueError(f"{parameter.name} is outside the configured search space")
