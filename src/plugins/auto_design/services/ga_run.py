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
from src.plugins.auto_design.services.fitness import fitness_calculator
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

        name = member_name(1, member)
        folder = generation_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{name}.sdb"

        # 8.2.1  open the reference model and give every frame a random allowed section
        genes = random_genes(options, ctx.rng)

        ctx.sap.open_model(ctx.sapPath)
        ctx.sap.unlock_model()

        for frame, section in genes.items():
            if section != ctx.frameSections[frame]:  # same as the reference: nothing to do
                ctx.sap.assign_frame_section(frame, section)

        # 8.2.2  Save As in the member's folder
        ctx.sap.save_model_as(path)

        # 8.2.3  fitness of the new model
        ctx.monitor.status(f"Generation 1: evaluating member {member} of {total}")
        individual = Individual(name, path, genes)
        individual.fitness = fitness_calculator(ctx.sap, path)
        ctx.population.append(individual)

    logger.info(
        "Step 8 - initial population: %d members in %s", len(ctx.population), generation_dir
    )

def run_ga(ctx: GAContext) -> None:
    # Steps in order; the first one is step FIRST_RUN_STEP.
    steps = (
        step5_material_types,
        step6_frame_sections,
        step7_geometry,
        step8_initial_population,
        # TODO: steps 9 ... 20
    )
    total = TOTAL_STEPS - FIRST_RUN_STEP + 1

    ctx.monitor.progress(0.0)
    prepare_database_folder(ctx)

    for done, step in enumerate(steps, start=1):
        step(ctx)
        ctx.monitor.progress(done / total)
