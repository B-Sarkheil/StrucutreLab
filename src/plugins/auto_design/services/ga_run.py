"""Auto Design - the run of the genetic algorithm, step by step (no Qt).

`GAContext` holds everything the steps share. Every step is a function
that reads and updates the context; `run_ga` calls them in order. It runs
in a worker thread (see `ui/wizard.py`).

Reporting: every step announces what it is doing with
`ctx.monitor.status(...)` (shown on the run page, and a point where the
user's Cancel takes effect), and `run_ga` reports the estimated progress
after every step. The estimate is temporary: it counts finished steps out
of `TOTAL_STEPS`; the final way of computing it comes when the whole
algorithm exists.
"""
from __future__ import annotations

import logging
import random
import shutil
from pathlib import Path
from collections import Counter
from dataclasses import dataclass, field, replace

from src.core.sap_client import SapClient
from src.plugins.auto_design.params import AutoDesignParams, SectionPermission
from src.plugins.auto_design.services.run_monitor import RunMonitor
from src.plugins.auto_design.services.section_materials import read_material_types
from src.plugins.auto_design.services.frame_assignments import read_frame_sections
from src.plugins.auto_design.services.model_geometry import (
    read_frame_connectivity,
    read_joint_coordinates,
)
from src.plugins.auto_design.services.fitness import fitness_calculator, fitness_value
from src.plugins.auto_design.services.genetic_operators import (
    random_cut_points,
    select_survivors,
    three_point_crossover,
    tournament_parents,
)
from src.plugins.auto_design.services.population import (
    Individual,
    build_gene_options,
    classify_frame,
    member_name,
    random_genes,
)
from src.plugins.auto_design.services.database_folder import (
    check_folder_usable,
    clear_folder,
    copy_member_model,
)

logger = logging.getLogger(__name__)

# The whole algorithm has 20 steps; steps 1-4 happen in the wizard pages
# (file, sections, settings, Simulate Evolution), so the run starts at 5.
TOTAL_STEPS = 20
FIRST_RUN_STEP = 5


@dataclass
class GAContext:
    sap: SapClient
    params: AutoDesignParams
    sections: list[SectionPermission]
    sapPath: str  # the reference .sdb chosen in step 1
    frameSections: dict[str, str] = field(default_factory=dict)  # frame -> section (step 6)
    jointCoordinates: dict[str, tuple[float, float, float]] = field(default_factory=dict)  # (step 7)
    frameConnectivity: dict[str, tuple[str, str]] = field(default_factory=dict)  # (step 7)
    population: list[Individual] = field(default_factory=list)  # generation 1 (step 8)
    offspring: list[Individual] = field(default_factory=list)  # children of the current iteration (9.1)
    generation: int = 1  # number of the generation in `population`
    rng: random.Random = field(default_factory=random.Random)
    monitor: RunMonitor = field(default_factory=RunMonitor)

def prepare_database_folder(ctx: GAContext) -> None:
    """Start of the run: clear the database folder (the user has confirmed it
    in the wizard). It is not one of the 20 steps, so it does not count in
    the progress."""

    ctx.monitor.status("Clearing the database folder")

    problem = check_folder_usable(ctx.params.modelsFolder, ctx.sapPath)

    if problem:
        raise ValueError(problem)

    # SAP2000 may still have a model of the previous run open (its files are
    # locked): open the reference model first, which is outside the folder.
    ctx.sap.open_model(ctx.sapPath)

    clear_folder(ctx.params.modelsFolder)


def step5_material_types(ctx: GAContext) -> None:
    """Step 5: store the SAP Material Type of every section of the model."""

    ctx.monitor.status("Reading the material type of every section")

    types = read_material_types(ctx.sap, [s.name for s in ctx.sections])
    ctx.sections = [replace(s, materialType=types[s.name]) for s in ctx.sections]

    counts = Counter(s.materialType or "(none)" for s in ctx.sections)
    logger.info("Step 5 - Material Types: %s", dict(counts))


def step6_frame_sections(ctx: GAContext) -> None:
    """Step 6: store the section assigned to every frame of the model."""

    ctx.monitor.status("Reading the section assigned to every frame")

    ctx.frameSections = read_frame_sections(ctx.sap)

    known = {s.name for s in ctx.sections}
    unknown = sorted({sec for sec in ctx.frameSections.values() if sec not in known})

    if unknown:
        logger.warning(
            "Step 6 - sections used by frames but not in the section list: %s", unknown
        )

    logger.info(
        "Step 6 - %d frames, %d different sections",
        len(ctx.frameSections),
        len(set(ctx.frameSections.values())),
    )


def step7_geometry(ctx: GAContext) -> None:
    """Step 7: store joint coordinates and the joints of every frame."""

    ctx.monitor.status("Reading joint coordinates and frame connectivity")

    ctx.jointCoordinates = read_joint_coordinates(ctx.sap)
    ctx.frameConnectivity = read_frame_connectivity(ctx.sap)

    # Consistency with step 6 and inside the geometry itself (warnings only).
    only_assigned = set(ctx.frameSections) - set(ctx.frameConnectivity)
    only_connected = set(ctx.frameConnectivity) - set(ctx.frameSections)

    if only_assigned or only_connected:
        logger.warning(
            "Step 7 - frames with a section but no connectivity: %s; "
            "frames with connectivity but no section: %s",
            sorted(only_assigned),
            sorted(only_connected),
        )

    missing_joints = sorted(
        {
            joint
            for pair in ctx.frameConnectivity.values()
            for joint in pair
            if joint not in ctx.jointCoordinates
        }
    )

    if missing_joints:
        logger.warning("Step 7 - joints used by frames without coordinates: %s", missing_joints)

    logger.info(
        "Step 7 - %d joints, %d frames",
        len(ctx.jointCoordinates),
        len(ctx.frameConnectivity),
    )


def _make_member(
    ctx: GAContext, generation: int, member: int, total: int, genes: dict[str, str]
) -> Individual:
    """Build one member of a generation and evaluate it (used by steps 8 and 9).

    The reference model is opened (clean start, no old results), every frame
    whose gene differs from the reference gets its section, the model is
    saved as `<modelsFolder>/Generation-<generation>/<name>/<name>.sdb`, and
    `fitness_calculator` is called on it.
    """

    name = member_name(generation, member)
    folder = Path(ctx.params.modelsFolder) / f"Generation-{generation}" / name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.sdb"

    ctx.sap.open_model(ctx.sapPath)
    ctx.sap.unlock_model()

    for frame, section in genes.items():
        if section != ctx.frameSections[frame]:  # same as the reference: nothing to do
            ctx.sap.assign_frame_section(frame, section)

    ctx.sap.save_model_as(path)

    ctx.monitor.status(f"Generation {generation}: evaluating member {member} of {total}")
    individual = Individual(name, path, genes)
    individual.fitness = fitness_calculator(ctx.sap, path)

    return individual


def step8_initial_population(ctx: GAContext) -> None:
    """Step 8: build the first generation (reference model + random members)."""

    # Final size is always even (members are paired later).
    total = ctx.params.popSize + ctx.params.popSize % 2

    # Roles and allowed sections do not change between members: compute once,
    # before any folder is created, so a problem stops the run at the start.
    ctx.monitor.status("Preparing the allowed sections of every frame")

    roles = {
        frame: classify_frame(
            frame, ctx.frameConnectivity, ctx.jointCoordinates, ctx.params.tolerance
        )
        for frame in ctx.frameSections
    }
    options = build_gene_options(ctx.frameSections, roles, ctx.sections)

    # 8.1  Generation-1 / Gen-1-1 with a copy of the reference file
    generation_dir = Path(ctx.params.modelsFolder) / "Generation-1"
    ctx.population = []
    ctx.generation = 1

    ctx.monitor.status(f"Generation 1: copying the reference model (member 1 of {total})")

    name = member_name(1, 1)
    folder = generation_dir / name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.sdb"
    shutil.copy2(ctx.sapPath, path)

    reference = Individual(name, path, dict(ctx.frameSections))
    ctx.population.append(reference)

    # fitness of the reference member, on its own copy (the original file is never touched)
    ctx.monitor.status(f"Generation 1: evaluating member 1 of {total}")
    ctx.sap.open_model(path)
    reference.fitness = fitness_calculator(ctx.sap, path)

    # 8.2  the other members
    for i in range(1, total):
        member = 1 + i
        ctx.monitor.status(f"Generation 1: building member {member} of {total}")

        # 8.2.1  a random allowed section for every frame, 8.2.2 Save As,
        # 8.2.3  fitness of the new model
        genes = random_genes(options, ctx.rng)
        ctx.population.append(_make_member(ctx, 1, member, total, genes))

    logger.info(
        "Step 8 - initial population: %d members in %s", len(ctx.population), generation_dir
    )


def step9_generations(ctx: GAContext) -> None:
    """Step 9: loop g = 1 .. genSize.

    9.1  Pair m = 1 .. N/2 (N = even population size) gives two children.
         The children are built INSIDE Generation-g, next to their parents,
         as members N+1 .. 2N (Gen-g-(N+1) ... Gen-g-2N): Generation-g then
         holds 2N members.
    9.2  The N members with the highest fitness of those 2N are copied to
         Generation-(g+1) (renamed Gen-(g+1)-1 ... Gen-(g+1)-N, best first)
         and become the population of the next iteration.

    9.3 and later are not written.
    """

    total = ctx.params.popSize + ctx.params.popSize % 2  # N
    pairs = total // 2  # 0.5 * (popSize + mod(popSize, 2))
    frames = list(ctx.frameSections)  # the DNA: genes in SAP table order

    if len(frames) < 3:
        raise ValueError(
            f"Three-point crossover needs at least 3 frames, the model has {len(frames)}."
        )

    def score(individual: Individual) -> float:
        return fitness_value(individual.fitness)  # larger = better

    for g in range(1, ctx.params.genSize + 1):
        ctx.generation = g
        ctx.offspring = []

        for m in range(1, pairs + 1):
            ctx.monitor.status(
                f"Generation {g}: pair {m} of {pairs} - selecting the parents"
            )

            # 9.1.1 / 9.1.2  tournament: the two best of tournamentSize random members
            parent_a, parent_b = tournament_parents(
                ctx.population, ctx.params.tournamentSize, ctx.rng, score
            )

            # 9.1.3  three different random cut points (1 .. number of genes)
            cuts = random_cut_points(len(frames), ctx.rng)

            # 9.1.4  three-point crossover
            children = three_point_crossover(frames, parent_a.genes, parent_b.genes, cuts)

            logger.info(
                "Step 9.1 - g=%d m=%d: parents %s x %s, cuts %s",
                g, m, parent_a.name, parent_b.name, cuts,
            )

            # 9.1.5  model and fitness of both children (members N+1 .. 2N)
            for offset, genes in enumerate(children):
                member = total + 2 * (m - 1) + 1 + offset
                ctx.monitor.status(
                    f"Generation {g}: building member {member} of {2 * total}"
                )
                ctx.offspring.append(_make_member(ctx, g, member, 2 * total, genes))

        logger.info(
            "Step 9.1 - g=%d: %d children in Generation-%d", g, len(ctx.offspring), g
        )

        _step9_2_next_generation(ctx, g, total, score)

        # TODO: 9.3 ...


def _step9_2_next_generation(ctx: GAContext, g: int, size: int, score) -> None:
    """Step 9.2: the `size` best of parents + children (2N members in
    Generation-g) are copied to Generation-(g+1) and become the population.

    Only the model file (.sdb, which keeps the analysis results) is copied,
    into `Generation-(g+1)/Gen-(g+1)-k/Gen-(g+1)-k.sdb`; the originals stay
    in Generation-g.
    """

    pool = ctx.population + ctx.offspring  # parents first: they win equal scores

    ctx.monitor.status(
        f"Generation {g + 1}: copying the best {size} of {len(pool)} members"
    )

    survivors = select_survivors(pool, score, size)

    # The last evaluated model is still open in SAP2000 (its file may be
    # locked): open the reference model, which is outside the database folder.
    ctx.sap.open_model(ctx.sapPath)

    generation_dir = Path(ctx.params.modelsFolder) / f"Generation-{g + 1}"
    next_population: list[Individual] = []

    for rank, individual in enumerate(survivors, start=1):
        ctx.monitor.raise_if_cancelled()

        name = member_name(g + 1, rank)
        path = copy_member_model(individual.path, generation_dir / name, name)
        next_population.append(Individual(name, path, dict(individual.genes), individual.fitness))

    ctx.population = next_population
    ctx.offspring = []
    ctx.generation = g + 1

    logger.info(
        "Step 9.2 - g=%d: %d members copied to %s", g, len(next_population), generation_dir
    )

def run_ga(ctx: GAContext) -> None:
    # Steps in order; the first one is step FIRST_RUN_STEP.
    steps = (
        step5_material_types,
        step6_frame_sections,
        step7_geometry,
        step8_initial_population,
        step9_generations,
        # TODO: steps 10 ... 20
    )
    total = TOTAL_STEPS - FIRST_RUN_STEP + 1

    ctx.monitor.progress(0.0)
    prepare_database_folder(ctx)

    for done, step in enumerate(steps, start=1):
        step(ctx)
        ctx.monitor.progress(done / total)
