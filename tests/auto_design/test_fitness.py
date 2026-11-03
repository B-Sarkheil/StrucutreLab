"""Tests of the CV formula and of the ranking (no SAP, no Qt)."""
import random
from pathlib import Path

import pytest

from src.plugins.auto_design.services.fitness import (
    CV_EPSILON,
    CvWeights,
    Fitness,
    compute_cv,
    governing_ratios,
    mean_violation,
    ranking_key,
)
from src.plugins.auto_design.services.genetic_operators import (
    select_survivors,
    tournament_parents,
)
from src.plugins.auto_design.services.population import Individual


def _fit(weight: float, cv: float) -> Fitness:
    return Fitness(weight, cv, cv, {}, 0.0, 0.0, 1)


def _member(name: str, weight: float, cv: float) -> Individual:
    return Individual(name, Path(name), {}, _fit(weight, cv))


def _rank(individual: Individual):
    return ranking_key(individual.fitness)


def test_governing_ratio_is_the_max_per_element():
    result = governing_ratios([{"a": 0.8, "b": 1.2}, {"a": 1.1}])

    assert result == {"a": 1.1, "b": 1.2}


def test_mean_violation_counts_only_ratios_above_one():
    assert mean_violation([0.5, 1.2, 1.5]) == pytest.approx((0.2 + 0.5) / 3)
    assert mean_violation([]) == 0.0


def test_cv_with_weights():
    weights = CvWeights(element=2.0, globalWeights={"drift": 3.0})
    cv, v_e, v_g = compute_cv({"a": 1.2, "b": 0.9}, {"drift": [1.1, 0.8]}, weights)

    assert v_e == pytest.approx(0.1)
    assert v_g["drift"] == pytest.approx(0.05)
    assert cv == pytest.approx(2.0 * 0.1 + 3.0 * 0.05)


def test_cv_is_zero_when_nothing_is_violated():
    cv, _v_e, _v_g = compute_cv({"a": 1.0, "b": 0.4}, {}, CvWeights())

    assert cv == 0.0


def test_global_constraint_without_weight_gets_one():
    cv, _v_e, _v_g = compute_cv({}, {"other": [1.5]}, CvWeights(globalWeights={}))

    assert cv == pytest.approx(0.5)


def test_feasible_members_come_first_by_weight_then_infeasible_by_cv():
    members = [
        _member("bad-light", 50.0, 0.4),
        _member("ok-heavy", 200.0, 0.0),
        _member("worse", 40.0, 0.9),
        _member("ok-light", 100.0, CV_EPSILON / 2),
    ]

    order = [m.name for m in sorted(members, key=_rank)]

    assert order == ["ok-light", "ok-heavy", "bad-light", "worse"]


def test_ranking_needs_a_fitness_object():
    with pytest.raises(ValueError):
        ranking_key(None)


def test_select_survivors_keeps_the_best_and_parents_win_ties():
    parent = _member("parent", 100.0, 0.0)
    child = _member("child", 100.0, 0.0)
    pool = [parent, _member("bad", 10.0, 0.5), child, _member("light", 80.0, 0.0)]

    best = select_survivors(pool, _rank, 3)

    assert [m.name for m in best] == ["light", "parent", "child"]


def test_tournament_takes_the_two_best():
    population = [_member("a", 300.0, 0.0), _member("b", 100.0, 0.0), _member("c", 200.0, 0.3)]

    first, second = tournament_parents(population, 3, random.Random(1), _rank)

    assert (first.name, second.name) == ("b", "a")
