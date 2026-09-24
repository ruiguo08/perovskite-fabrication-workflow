"""Pluggable recipe suggestion strategies."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import product
from random import Random
from typing import Any, Protocol, Sequence

from .recipe import DepositionRecipe
from .records import ExperimentRecord, ExperimentStatus
from .search_space import ChoiceParameter, FloatParameter, IntegerParameter, SearchSpace


class SuggestionStrategy(Protocol):
    """Interface for random, Bayesian, or other optimization backends."""

    def suggest(self, search_space: SearchSpace, history: Sequence[ExperimentRecord]) -> DepositionRecipe: ...


@dataclass
class RandomStrategy:
    """Reproducible initial-design baseline that avoids duplicate recipes."""

    seed: int | None = None
    max_attempts: int = 1_000
    _random: Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._random = Random(self.seed)

    def suggest(self, search_space: SearchSpace, history: Sequence[ExperimentRecord]) -> DepositionRecipe:
        observed = {_recipe_key(search_space, record.recipe) for record in history}
        for _ in range(self.max_attempts):
            values = search_space.sample(self._random)
            search_space.validate(values)
            recipe = DepositionRecipe.from_mapping(values)
            if _recipe_key(search_space, recipe) not in observed:
                return recipe
        raise RuntimeError("could not find an untried recipe within max_attempts")


@dataclass
class BayesianStrategy:
    """Lightweight Bayesian-optimization strategy using stored experiment history.

    The implementation intentionally avoids heavyweight numerical dependencies.
    Completed experiments fit a simple radial-basis surrogate over normalized
    recipe parameters. Failed experiments are retained as infeasible observations:
    exact failed recipes are never repeated, and candidates near failures receive
    a feasibility penalty in the acquisition score.
    """

    seed: int | None = None
    initial_random: int = 3
    candidate_count: int = 512
    exploration_weight: float = 0.25
    failure_penalty_radius: float = 0.20
    max_attempts: int = 2_000
    _random: Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._random = Random(self.seed)

    def suggest(self, search_space: SearchSpace, history: Sequence[ExperimentRecord]) -> DepositionRecipe:
        observed = {_recipe_key(search_space, record.recipe) for record in history}
        completed = [record for record in history if record.status == ExperimentStatus.COMPLETED and "pce" in record.metrics]
        failed = [record for record in history if record.status == ExperimentStatus.FAILED]

        if len(completed) < self.initial_random:
            return self._random_untried(search_space, observed)

        candidates = self._candidate_recipes(search_space, observed)
        if not candidates:
            raise RuntimeError("could not find an untried recipe candidate")

        completed_vectors = [_encode_recipe(search_space, record.recipe) for record in completed]
        completed_scores = [record.metrics["pce"] for record in completed]
        failed_vectors = [_encode_recipe(search_space, record.recipe) for record in failed]

        best_recipe, _ = max(
            candidates,
            key=lambda item: self._acquisition(item[1], completed_vectors, completed_scores, failed_vectors),
        )
        return best_recipe

    def _random_untried(
        self,
        search_space: SearchSpace,
        observed: set[tuple[Any, ...]],
    ) -> DepositionRecipe:
        for _ in range(self.max_attempts):
            values = search_space.sample(self._random)
            search_space.validate(values)
            recipe = DepositionRecipe.from_mapping(values)
            if _recipe_key(search_space, recipe) not in observed:
                return recipe
        raise RuntimeError("could not find an untried recipe within max_attempts")

    def _candidate_recipes(
        self,
        search_space: SearchSpace,
        observed: set[tuple[Any, ...]],
    ) -> list[tuple[DepositionRecipe, list[float]]]:
        candidates: dict[tuple[Any, ...], tuple[DepositionRecipe, list[float]]] = {}
        for values in _grid_values(search_space, self.candidate_count):
            self._add_candidate(search_space, observed, candidates, values)
        for _ in range(self.candidate_count):
            self._add_candidate(search_space, observed, candidates, search_space.sample(self._random))
        return list(candidates.values())

    @staticmethod
    def _add_candidate(
        search_space: SearchSpace,
        observed: set[tuple[Any, ...]],
        candidates: dict[tuple[Any, ...], tuple[DepositionRecipe, list[float]]],
        values: dict[str, Any],
    ) -> None:
        search_space.validate(values)
        recipe = DepositionRecipe.from_mapping(values)
        key = _recipe_key(search_space, recipe)
        if key in observed or key in candidates:
            return
        candidates[key] = (recipe, _encode_values(search_space, values))

    def _acquisition(
        self,
        candidate: list[float],
        completed_vectors: list[list[float]],
        completed_scores: list[float],
        failed_vectors: list[list[float]],
    ) -> float:
        weights = [_rbf_similarity(candidate, vector) for vector in completed_vectors]
        weight_sum = sum(weights)
        if weight_sum == 0:
            mean = sum(completed_scores) / len(completed_scores)
            variance = 0.0
        else:
            mean = sum(weight * score for weight, score in zip(weights, completed_scores)) / weight_sum
            variance = sum(weight * (score - mean) ** 2 for weight, score in zip(weights, completed_scores)) / weight_sum
        uncertainty = math.sqrt(max(variance, 0.0)) / math.sqrt(1.0 + weight_sum)
        feasibility = self._feasibility(candidate, failed_vectors)
        return (mean + self.exploration_weight * uncertainty) * feasibility

    def _feasibility(self, candidate: list[float], failed_vectors: list[list[float]]) -> float:
        if not failed_vectors:
            return 1.0
        nearest = min(_euclidean_distance(candidate, vector) for vector in failed_vectors)
        if nearest == 0:
            return 0.0
        if nearest >= self.failure_penalty_radius:
            return 1.0
        return nearest / self.failure_penalty_radius


def _grid_values(search_space: SearchSpace, limit: int) -> list[dict[str, Any]]:
    value_options: list[list[Any]] = []
    total = 1
    for parameter in search_space.parameters:
        if isinstance(parameter, IntegerParameter):
            options = list(range(parameter.lower, parameter.upper + 1))
        elif isinstance(parameter, ChoiceParameter):
            options = list(parameter.choices)
        elif isinstance(parameter, FloatParameter):
            midpoint = (parameter.lower + parameter.upper) / 2
            options = [parameter.lower, midpoint, parameter.upper]
        else:
            return []
        total *= len(options)
        if total > limit:
            return []
        value_options.append(options)
    return [
        {parameter.name: value for parameter, value in zip(search_space.parameters, values)}
        for values in product(*value_options)
    ]


def _encode_recipe(search_space: SearchSpace, recipe: DepositionRecipe) -> list[float]:
    return _encode_values(search_space, recipe.to_dict())


def _recipe_key(search_space: SearchSpace, recipe: DepositionRecipe) -> tuple[Any, ...]:
    """Identify a tried BO point independently of fixed recipe context."""

    values = recipe.to_dict()
    return tuple(values[parameter.name] for parameter in search_space.parameters)


def _encode_values(search_space: SearchSpace, values: dict[str, Any]) -> list[float]:
    encoded: list[float] = []
    for parameter in search_space.parameters:
        value = values[parameter.name]
        if isinstance(parameter, (FloatParameter, IntegerParameter)):
            span = parameter.upper - parameter.lower
            encoded.append(0.0 if span == 0 else (float(value) - parameter.lower) / span)
        elif isinstance(parameter, ChoiceParameter):
            # One-hot encoding keeps unordered categories equidistant. This is
            # important for valves, solvent systems, and device architectures.
            if value not in parameter.choices:
                raise ValueError(f"{parameter.name} is outside the configured search space")
            encoded.extend(1.0 if value == choice else 0.0 for choice in parameter.choices)
        else:
            encoded.append(0.0)
    return encoded


def _rbf_similarity(left: list[float], right: list[float]) -> float:
    return math.exp(-_euclidean_distance(left, right) ** 2)


def _euclidean_distance(left: list[float], right: list[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))
