"""Auto Design - the run of the genetic algorithm, step by step (no Qt).

`GAContext` holds everything the steps share. Every step is a function
that reads and updates the context; `run_ga` calls them in order. It runs
in a worker thread (see `ui/wizard.py`).

Reporting: every step announces what it is doing with
`ctx.monitor.status(...)` (shown on the run page, and a point where the
user's Cancel takes effect). The progress is real and counted in members
(`ctx.totalMembers`, `ctx.doneMembers`, `_member_done`).

Steps 1-4 are the wizard pages (1 reference file, 2 allowed sections, 3 frame
types, 4.1 linked frames, 4.2 constraint settings, 4.3 GA settings + the
Simulate Evolution button); the run starts at step 5.

Linked frames (step 4.1): frames of one group share ONE gene. The DNA is a
list of units (`ctx.units`, see `gene_groups.py`): random members and the
crossover work on units, and the reference model (member 1) is repaired so
that it respects the links.
"""
from __future__ import annotations

import logging
import random
import shutil
from pathlib import Path
from collections import Counter
from dataclasses import dataclass, field, replace

from src.core.sap_client import SapClient
from src.plugins.auto_design.params import AutoDesignParams, ConstraintParams, SectionPermission
from src.plugins.auto_design.services.run_monitor import GenerationStats, RunMonitor
from src.plugins.auto_design.services.section_materials import read_material_types
from src.plugins.auto_design.services.section_areas import read_section_areas
from src.plugins.auto_design.services.frame_assignments import read_frame_sections
from src.plugins.auto_design.services.model_geometry import (
    read_frame_connectivity,
    read_joint_coordinates,
)
from src.plugins.auto_design.services.fitness import CvWeights, fitness_calculator, ranking_key, selection_key

from src.plugins.auto_design.services.gene_groups import (
    build_units,
    random_unit_genes,
    repair_genes,
    unit_options,
)
from src.plugins.auto_design.services.genetic_operators import (
    random_cut_points,
    select_survivors,
    three_point_crossover,
    tournament_parents,
)
from src.plugins.auto_design.services.database_folder import (
    check_folder_usable,
    clear_folder,
    copy_member_model,
)
from src.plugins.auto_design.services.deflection import (
    DeflectionSettings,
    find_cantilever_beams,
)
from src.plugins.auto_design.services.population import (
    BEAM,
    COLUMN,
    Individual,
    build_gene_options,
    member_name,
)
from src.plugins.auto_design.services.genetic_operators import crossover_swaps
from src.plugins.auto_design.services.mutation import mutate_child
from src.plugins.auto_design.services.section_ordering import (
    KINDS, read_section_properties, sort_strong_to_weak,
)
from src.plugins.auto_design.services.first_generation import list_member_models
from src.plugins.auto_design.services.column_width_rule import (
    ColumnRule, build_column_links, count_violations, prune_beam_options,
    read_section_dimensions, repair_columns,
)


logger = logging.getLogger(__name__)

# Left over from the old progress estimate (not used any more).
TOTAL_STEPS = 20
FIRST_RUN_STEP = 5


@dataclass
class GAContext:
    sap: SapClient
    params: AutoDesignParams
    sections: list[SectionPermission]
    sapPath: str  # the reference .sdb chosen in step 1
    frameRoles: dict[str, str] = field(default_factory=dict)  # frame -> role (wizard, "Frame types" page)
    frameLinks: list[tuple[str, ...]] = field(default_factory=list)  # linked frames (wizard, step 4.1)
    constraints: ConstraintParams | None = None  # constraint settings (wizard, step 4.2)
    firstGenerationFolder: str = ""  # resume: folder of an existing first generation ("" = random initial population)
    frameSections: dict[str, str] = field(default_factory=dict)  # frame -> section (step 6)
    jointCoordinates: dict[str, tuple[float, float, float]] = field(default_factory=dict)  # (step 7)
    frameConnectivity: dict[str, tuple[str, str]] = field(default_factory=dict)  # (step 7)
    units: list[tuple[str, ...]] = field(default_factory=list)  # the DNA: frames that share a gene (step 8)
    population: list[Individual] = field(default_factory=list)  # generation 1 (step 8)
    referenceFitness: object | None = None  # fitness of member 1 of generation 1 (step 8; not used by the pages)
    firstBestFitness: object | None = None  # fitness of the best member of generation 1 (end of step 8), for the % change
    deflection: DeflectionSettings | None = None  # beam deflection constraint (step 8), None = off
    dcrGoal: float = 1.0  # DCR Goal of step 4.2 (stress ratios are divided by it)
    cvWeights: CvWeights = field(default_factory=CvWeights)  # w_e, w_d of step 4.2
    offspring: list[Individual] = field(default_factory=list)  # children of the current iteration (9.1)
    generation: int = 1  # number of the generation in `population`
    rng: random.Random = field(default_factory=random.Random)
    monitor: RunMonitor = field(default_factory=RunMonitor)
    totalMembers: int = 0  # members to evaluate in the whole run (step 8 + step 9)
    doneMembers: int = 0  # members evaluated so far (progress)
    unitChoices: list[list[str]] = field(default_factory=list)  # allowed sections of every unit (step 8)
    unitOrders: dict[str, list[list[str]]] = field(default_factory=dict)  # kind -> strong->weak list per unit (step 8)
    columnRule: ColumnRule | None = None  # column width / height rule (step 8.0), None = off


def prepare_database_folder(ctx: GAContext) -> None:
    """Start of the run: clear the database folder (the user has confirmed it
    in the wizard). It belongs to step 4.3 (the Simulate Evolution button asks the user to confirm it) and does not count in the progress."""

    ctx.monitor.status("Clearing the database folder")

    problem = check_folder_usable(
        ctx.params.modelsFolder, ctx.sapPath, ctx.firstGenerationFolder
    )

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


def _deflection_settings(ctx: GAContext) -> DeflectionSettings | None:
    """Beam deflection constraint from the constraint settings (None = off)."""

    constraints = ctx.constraints

    if constraints is None or not constraints.deflectionCombo:
        return None

    beams = tuple(f for f in ctx.frameSections if ctx.frameRoles.get(f) == BEAM)

    if not beams:
        logger.warning("Deflection constraint: the model has no frame of type Beam")
        return None

    cantilevers = find_cantilever_beams(ctx.sap, beams, ctx.frameConnectivity)

    logger.info(
        "Deflection constraint: combination '%s', L/%d, %d beams, "
        "%d cantilever beams (limit doubled)",
        constraints.deflectionCombo, constraints.deflectionDivisor,
        len(beams), len(cantilevers),
    )

    return DeflectionSettings(
        combo=constraints.deflectionCombo,
        divisor=constraints.deflectionDivisor,
        beams=beams,
        cantilevers=cantilevers,
    )


def _apply_constraint_settings(ctx: GAContext) -> None:
    """DCR goal and the CV weights from the constraint settings (step 4.2):
    Element Constraint Coefficient = w_e, General Constraint Coefficient = w_d."""

    constraints = ctx.constraints

    if constraints is None:
        return

    ctx.dcrGoal = constraints.dcrGoal
    ctx.cvWeights = CvWeights(
        element=constraints.elementCoefficient,
        globalWeights={"drift": constraints.generalCoefficient},
    )

    logger.info(
        "Constraint settings used: DCR goal=%.4g, w_e=%.4g, w_d(drift)=%.4g",
        ctx.dcrGoal, ctx.cvWeights.element, constraints.generalCoefficient,
    )


def _evaluate(ctx: GAContext, path: Path):
    """fitness_calculator with all the settings of the run."""

    return fitness_calculator(
        ctx.sap,
        path,
        weights=ctx.cvWeights,
        deflection=ctx.deflection,
        dcr_goal=ctx.dcrGoal,
        flexure_ratios=ctx.params.directedMutationPercent > 0,
    )


def _member_done(ctx: GAContext) -> None:
    """One member has been evaluated: report the real progress of the run."""

    ctx.doneMembers += 1
    ctx.monitor.progress(ctx.doneMembers / max(1, ctx.totalMembers))


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
    individual.fitness = _evaluate(ctx, path)
    _member_done(ctx)

    return individual

def _report_generation(ctx: GAContext, generation: int) -> None:
    """Send the numbers of the current population to the run page
    (generation 1 = the initial population)."""

    best = min(ctx.population, key=selection_key)

    mean_weight = sum(m.fitness.weight for m in ctx.population) / len(ctx.population)

    ctx.monitor.generation(
        GenerationStats(
            generation=generation,
            bestWeight=best.fitness.weight,
            meanWeight=mean_weight,
            meanRatio=best.fitness.meanRatio,
            maxRatio=best.fitness.maxRatio,
            meanDeflection=best.fitness.meanDeflection,
            maxDeflection=best.fitness.maxDeflection,
            bestName=best.name,
            cv=best.fitness.cv,
        )
    )

def _apply_column_rule(ctx: GAContext, options: dict[str, list[str]]) -> dict[str, list[str]]:
    """Step 8.0: prune the beam options and build the column rule data.
    The reference model must be open."""

    dims = read_section_dimensions(ctx.sap)
    column_sections = [s.name for s in ctx.sections if s.allowedForColumn]
    options, removed = prune_beam_options(options, ctx.frameRoles, dims, column_sections)

    links = build_column_links(
        ctx.frameRoles, ctx.frameConnectivity, ctx.jointCoordinates, ctx.sap.frame_local_axes
    )
    ctx.columnRule = ColumnRule(
        columns=frozenset(f for f, role in ctx.frameRoles.items() if role == COLUMN),
        links=links,
        dims=dims,
        areas=read_section_areas(ctx.sap),
    )

    logger.info(
        "Step 8.0 - column width rule: %d columns with beams (%d beams linked), "
        "%d beam option(s) removed",
        len(links), sum(len(v) for v in links.values()), removed,
    )

    return options


def _rule_violations(ctx: GAContext, genes: dict[str, str]) -> int:
    return count_violations(genes, ctx.columnRule) if ctx.columnRule is not None else 0


def _mark_rule_violations(ctx: GAContext) -> None:
    for member in ctx.population:
        member.ruleViolations = _rule_violations(ctx, member.genes)


def _prepare_dna(ctx: GAContext) -> int:
    """Part of step 8 shared by the random start and the resume: check the
    frame roles, build the deflection settings and the constraint settings, the
    DNA (units), the allowed sections of every unit and, with directed
    mutation, the strong -> weak orders. The reference model must be open.
    Returns the number of linked frames."""

    # The role of every frame (column, beam, ...) was decided once, on the
    # "Frame types" page (step 3), from the reference model. Every frame read in
    # step 6 must have one.
    missing_roles = sorted(set(ctx.frameSections) - set(ctx.frameRoles))

    if missing_roles:
        shown = ", ".join(missing_roles[:10])
        more = f" (and {len(missing_roles) - 10} more)" if len(missing_roles) > 10 else ""
        raise ValueError(
            f"{len(missing_roles)} frame(s) have no type from the Frame types page: "
            f"{shown}{more}. Go back and classify the frames again."
        )

    ctx.deflection = _deflection_settings(ctx)
    _apply_constraint_settings(ctx)

    # Allowed sections do not change between members: compute once, before
    # any folder is created, so a problem stops the run at the start.
    ctx.monitor.status("Preparing the allowed sections of every frame")

    options = build_gene_options(ctx.frameSections, ctx.frameRoles, ctx.sections)

    ctx.columnRule = None

    if ctx.constraints is not None and ctx.constraints.columnWidthRule:
        ctx.monitor.status("Step 8.0: preparing the column width / height rule")
        options = _apply_column_rule(ctx, options)

    # The DNA: one unit per group of linked frames, one per other frame.
    ctx.units = build_units(ctx.frameSections, ctx.frameLinks)
    ctx.unitChoices = unit_options(ctx.units, options)

    if ctx.params.directedMutationPercent > 0:
        ctx.monitor.status("Reading Z33, Z22, I33 and Area of the sections for the directed mutation")
        properties = read_section_properties(ctx.sap)
        ctx.unitOrders = {
            kind: [sort_strong_to_weak(c, properties, kind) for c in ctx.unitChoices]
            for kind in KINDS
        }

    linked_frames = sum(len(unit) for unit in ctx.units if len(unit) > 1)

    logger.info(
        "Step 8 - DNA: %d frames in %d genes (%d groups of linked frames, %d linked frames)",
        len(ctx.frameSections),
        len(ctx.units),
        sum(len(unit) > 1 for unit in ctx.units),
        linked_frames,
    )

    return linked_frames


def step8_initial_population(ctx: GAContext) -> None:
    """Step 8: build the first generation (reference model + random members).

    Member 1 is the reference model; when frames are linked (step 4.1) and
    the reference gives them different sections, member 1 is the REPAIRED
    reference (the largest section of every group is given to the whole
    group). The other members get one random section per unit.
    """

    # Final size is always even (members are paired later).
    total = ctx.params.popSize + ctx.params.popSize % 2

    # Whole run: N members of generation 1 + N children in each of the
    # genSize - 1 iterations of step 9.
    ctx.totalMembers = total * (1 + (ctx.params.genSize - 1))
    ctx.doneMembers = 0

    linked_frames = _prepare_dna(ctx)
    unit_choices = ctx.unitChoices

    # Member 1: the reference model, repaired when the links ask for it.
    reference_genes = dict(ctx.frameSections)

    if linked_frames:
        ctx.monitor.status("Linked frames: giving the same section to every group of the reference model")
        areas = read_section_areas(ctx.sap)
        reference_genes = repair_genes(reference_genes, ctx.units, unit_choices, areas)

    repaired = reference_genes != ctx.frameSections

    # 8.1  Generation-1 / Gen-1-1 with a copy of the reference file
    generation_dir = Path(ctx.params.modelsFolder) / "Generation-1"
    ctx.population = []
    ctx.generation = 1

    if repaired:
        changed = sum(reference_genes[f] != ctx.frameSections[f] for f in reference_genes)
        logger.info("Step 8 - the reference model was repaired: %d frames changed", changed)
        ctx.monitor.status(f"Generation 1: building the repaired reference model (member 1 of {total})")
        reference = _make_member(ctx, 1, 1, total, reference_genes)
    else:
        ctx.monitor.status(f"Generation 1: copying the reference model (member 1 of {total})")

        name = member_name(1, 1)
        folder = generation_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{name}.sdb"
        shutil.copy2(ctx.sapPath, path)

        reference = Individual(name, path, dict(ctx.frameSections))

        # fitness of the reference member, on its own copy (the original file is never touched)
        ctx.monitor.status(f"Generation 1: evaluating member 1 of {total}")
        ctx.sap.open_model(path)
        reference.fitness = _evaluate(ctx, path)
        _member_done(ctx)

    ctx.population.append(reference)
    ctx.referenceFitness = reference.fitness

    # 8.2  the other members
    for i in range(1, total):
        member = 1 + i
        ctx.monitor.status(f"Generation 1: building member {member} of {total}")

        # 8.2.1  a random allowed section for every unit, 8.2.2 Save As,
        # 8.2.3  fitness of the new model
        genes = random_unit_genes(ctx.units, unit_choices, ctx.rng)
        ctx.population.append(_make_member(ctx, 1, member, total, genes))

    logger.info(
        "Step 8 - initial population: %d members in %s", len(ctx.population), generation_dir
    )

    # best member of generation 1 by the GA ranking (same member the run page uses as its base)
    _mark_rule_violations(ctx)  # generation 1 is not repaired: only marked
    ctx.firstBestFitness = min(ctx.population, key=selection_key).fitness

    _report_generation(ctx, 1)


def step8_resume_population(ctx: GAContext) -> None:
    """Step 8 of a resume: the random initial population is NOT built. The
    models of the first generation folder (one sub folder per model, natural
    order of the names) are copied to Generation-1 as Gen-1-1 ... Gen-1-P and
    every copy is evaluated (the genes are read from the model, and the
    fitness is needed for the ranking and the directed mutation). The first
    model is the reference model of the run (`ctx.sapPath`). The run goes on
    with step 9."""

    models = list_member_models(ctx.firstGenerationFolder)
    count = len(models)

    if count != ctx.params.popSize:
        raise ValueError(
            f"The first generation folder holds {count} models but the population size is "
            f"{ctx.params.popSize}. The folder changed after the settings were made: "
            "go back and check the settings again."
        )

    pairs_size = count + count % 2  # N used by step 9 (even)

    # Whole run: the P models of generation 1 + N children in each of the
    # genSize - 1 iterations of step 9.
    ctx.totalMembers = count + (ctx.params.genSize - 1) * pairs_size
    ctx.doneMembers = 0

    _prepare_dna(ctx)  # the reference model is still open here

    generation_dir = Path(ctx.params.modelsFolder) / "Generation-1"
    reference_frames = set(ctx.frameSections)

    ctx.population = []
    ctx.generation = 1

    for position, (source_name, source) in enumerate(models, start=1):
        name = member_name(1, position)

        ctx.monitor.status(
            f"Generation 1: copying and evaluating model {position} of {count} ({source_name})"
        )

        path = copy_member_model(source, generation_dir / name, name)

        ctx.sap.open_model(path)
        found = read_frame_sections(ctx.sap)

        if set(found) != reference_frames:
            missing = sorted(reference_frames - set(found))[:5]
            extra = sorted(set(found) - reference_frames)[:5]
            raise ValueError(
                f"The model of '{source_name}' does not have the same frames as the reference "
                f"model (missing: {missing}, extra: {extra}). All models of the first "
                "generation must have the same structure."
            )

        genes = {frame: found[frame] for frame in ctx.frameSections}  # reference frame order

        broken = sum(len({genes[f] for f in unit}) > 1 for unit in ctx.units if len(unit) > 1)

        if broken:
            logger.warning(
                "Step 8 - %s: %d group(s) of linked frames do not have one section", name, broken
            )

        individual = Individual(name, path, genes)
        individual.fitness = _evaluate(ctx, path)
        individual.ruleViolations = _rule_violations(ctx, genes)
        _member_done(ctx)
        ctx.population.append(individual)

    ctx.referenceFitness = ctx.population[0].fitness
    ctx.firstBestFitness = min(ctx.population, key=selection_key).fitness

    logger.info(
        "Step 8 - resume: %d models of %s copied to %s (random initial population skipped)",
        count, ctx.firstGenerationFolder, generation_dir,
    )

    _report_generation(ctx, 1)


def step9_generations(ctx: GAContext) -> None:
    """Step 9: loop g = 1 .. genSize-1.

    9.1  Pair m = 1 .. N/2 (N = even population size) gives two children.
         The children are built INSIDE Generation-g, next to their parents,
         as members N+1 .. 2N (Gen-g-(N+1) ... Gen-g-2N): Generation-g then
         holds 2N members. All the operators work on the units of the DNA
         (`ctx.units`): the number of genes is the number of units, and the
         frames of a unit always come from the same parent.
         9.1.1 / 9.1.2  tournament selection of the two parents,
         9.1.3          three random cut points,
         9.1.4          three-point crossover,
         9.1.5          directed and random mutation of each child,
         9.1.6          column width / height rule: the columns of each child
                        are repaired (only when the rule is switched on in
                        the constraint settings, see `column_width_rule.py`),
         9.1.7          model and fitness of both children.
    9.2  The N best members of those 2N (`selection_key`: a member that
         breaks the column width / height rule is behind every member that
         does not, then the feasible / infeasible ranking) are copied to
         Generation-(g+1) (renamed Gen-(g+1)-1 ... Gen-(g+1)-N, best first)
         and become the population of the next iteration.

    Generation 1 is not repaired (it is only marked); the rule is applied to
    every child, so from generation 2 on the members that break it are
    ranked last and normally disappear at step 9.2.

    9.3 and later are not written.
    """

    total = ctx.params.popSize + ctx.params.popSize % 2  # N
    pairs = total // 2  # 0.5 * (popSize + mod(popSize, 2))
    units = ctx.units  # the DNA: genes in SAP table order (linked frames = one gene)

    if len(units) < 3:
        raise ValueError(
            f"Three-point crossover needs at least 3 genes, the model has {len(units)} "
            "(linked frames count as one gene)."
        )

    def rank(individual):
        return ranking_key(individual.fitness)

    for g in range(1, ctx.params.genSize):
        ctx.generation = g
        ctx.offspring = []

        for m in range(1, pairs + 1):
            ctx.monitor.status(
                f"Generation {g}: pair {m} of {pairs} - selecting the parents"
            )

            # 9.1.1 / 9.1.2  tournament: the two best of tournamentSize random members
            parent_a, parent_b = tournament_parents(
                ctx.population, ctx.params.tournamentSize, ctx.rng, rank
            )

            # 9.1.3  three different random cut points (1 .. number of genes = units)
            cuts = random_cut_points(len(units), ctx.rng)

            # 9.1.4  three-point crossover
            children = three_point_crossover(units, parent_a.genes, parent_b.genes, cuts)
            directed = ctx.params.directedMutationPercent
            randomly = ctx.params.randomMutationPercent

            # 9.1.5  directed and random mutation
            if directed > 0 or randomly > 0:
                swaps = crossover_swaps(len(units), cuts)
                sources = (
                    [(parent_b if s else parent_a).fitness for s in swaps],
                    [(parent_a if s else parent_b).fitness for s in swaps],
                )
                children = tuple(
                    mutate_child(child, units, ctx.unitChoices, ctx.unitOrders, src,
                                 ctx.dcrGoal, directed, randomly, ctx.rng)
                    for child, src in zip(children, sources)
                )

            logger.info(
                "Step 9.1 - g=%d m=%d: parents %s x %s, cuts %s",
                g, m, parent_a.name, parent_b.name, cuts,
            )

            # 9.1.6  column width / height rule: repair the columns of both children
            if ctx.columnRule is not None:
                repaired = [
                    repair_columns(child, units, ctx.unitChoices, ctx.columnRule)
                    for child in children
                ]
                children = tuple(genes for genes, _count in repaired)
                logger.info(
                    "Step 9.1.6 - g=%d m=%d: column repair changed %d and %d unit(s)",
                    g, m, repaired[0][1], repaired[1][1],
                )

            # 9.1.7  model and fitness of both children (members N+1 .. 2N)
            for offset, genes in enumerate(children):
                member = total + 2 * (m - 1) + 1 + offset
                ctx.monitor.status(
                    f"Generation {g}: building member {member} of {2 * total}"
                )
                ctx.offspring.append(_make_member(ctx, g, member, 2 * total, genes))

        logger.info(
            "Step 9.1 - g=%d: %d children in Generation-%d", g, len(ctx.offspring), g
        )

        _step9_2_next_generation(ctx, g, total, selection_key)
        _report_generation(ctx, g + 1)


def _step9_2_next_generation(ctx: GAContext, g: int, size: int, rank) -> None:
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

    survivors = select_survivors(pool, rank, size)

    # The last evaluated model is still open in SAP2000 (its file may be
    # locked): open the reference model, which is outside the database folder.
    ctx.sap.open_model(ctx.sapPath)

    generation_dir = Path(ctx.params.modelsFolder) / f"Generation-{g + 1}"
    next_population: list[Individual] = []

    for position, individual in enumerate(survivors, start=1):
        ctx.monitor.raise_if_cancelled()

        name = member_name(g + 1, position)
        path = copy_member_model(individual.path, generation_dir / name, name)
        next_population.append(
            Individual(name, path, dict(individual.genes), individual.fitness, individual.ruleViolations)
        )

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
        step8_resume_population if ctx.firstGenerationFolder else step8_initial_population,
        step9_generations,
    )

    ctx.monitor.progress(0.0)
    prepare_database_folder(ctx)

    for step in steps:
        step(ctx)
