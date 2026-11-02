import random

import pytest

from src.plugins.auto_design.services.genetic_operators import (
    random_cut_points,
    three_point_crossover,
    tournament_parents,
)
from src.plugins.auto_design.services.population import Individual


def test_crossover_swaps_parts_two_and_four():
    frames = [f"F{i}" for i in range(1, 11)]
    a = {f: "A" for f in frames}
    b = {f: "B" for f in frames}

    c1, c2 = three_point_crossover(frames, a, b, (2, 5, 8))

    assert [c1[f] for f in frames] == list("AABBBAAABB")
    assert [c2[f] for f in frames] == list("BBAAABBBAA")


def test_crossover_cut_at_last_gene_gives_empty_fourth_part():
    frames = ["F1", "F2", "F3"]
    a = {f: "A" for f in frames}
    b = {f: "B" for f in frames}

    c1, c2 = three_point_crossover(frames, a, b, (1, 2, 3))

    assert [c1[f] for f in frames] == list("ABA")
    assert [c2[f] for f in frames] == list("BAB")


def test_cut_points_are_different_sorted_and_in_range():
    rng = random.Random(1)

    for _ in range(200):
        cuts = random_cut_points(3, rng)
        assert cuts == (1, 2, 3)

        cuts = random_cut_points(50, rng)
        assert len(set(cuts)) == 3
        assert list(cuts) == sorted(cuts)
        assert 1 <= cuts[0] and cuts[2] <= 50


def test_cut_points_need_three_genes():
    with pytest.raises(ValueError):
        random_cut_points(2, random.Random())


def _population(values):
    return [Individual(f"Gen-1-{i + 1}", None, {}, v) for i, v in enumerate(values)]


def test_tournament_takes_the_two_best_of_the_drawn_members():
    population = _population([1, 9, 5, 7, 3])

    # tournament as large as the population: always the two highest
    a, b = tournament_parents(population, 5, random.Random(0), lambda i: i.fitness)

    assert (a.fitness, b.fitness) == (9, 7)


def test_tournament_parents_are_different_members():
    population = _population(list(range(20)))
    rng = random.Random(3)

    for _ in range(100):
        a, b = tournament_parents(population, 4, rng, lambda i: i.fitness)
        assert a is not b


def test_tournament_size_limits():
    population = _population([1, 2, 3])

    with pytest.raises(ValueError):
        tournament_parents(population, 1, random.Random(), lambda i: i.fitness)

    with pytest.raises(ValueError):
        tournament_parents(population, 4, random.Random(), lambda i: i.fitness)


def test_select_survivors_keeps_the_best_n_best_first():
    from src.plugins.auto_design.services.genetic_operators import select_survivors

    pool = _population([5, 1, 9, 3, 7, 2])
    survivors = select_survivors(pool, lambda i: i.fitness, 3)

    assert [i.fitness for i in survivors] == [9, 7, 5]


def test_select_survivors_tie_favors_the_first_in_the_pool():
    from src.plugins.auto_design.services.genetic_operators import select_survivors

    pool = _population([4, 4])  # parent first, child second
    survivors = select_survivors(pool, lambda i: i.fitness, 1)

    assert survivors[0] is pool[0]


def test_select_survivors_cannot_keep_more_than_the_pool():
    from src.plugins.auto_design.services.genetic_operators import select_survivors

    with pytest.raises(ValueError):
        select_survivors(_population([1, 2]), lambda i: i.fitness, 3)
