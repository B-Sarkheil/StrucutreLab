"""Auto Design wizard: the container that moves between the plugin's pages."""
from __future__ import annotations

import logging

from PySide6.QtWidgets import QMessageBox, QStackedWidget, QWidget
from PySide6.QtCore import QThread, Signal

from src.plugins.auto_design.params import AutoDesignParams, SectionPermission
from src.plugins.auto_design.ui.ga_settings_page import GASettingsPage
from src.plugins.auto_design.ui.page import AutoDesignPage
from src.plugins.auto_design.ui.roles_page import FrameRolesPage
from src.plugins.auto_design.ui.run_page import (
    CANCELLED,
    FAILED,
    FINISHED,
    RunPage,
)
from src.plugins.auto_design.ui.sections_page import SectionsPage
from src.plugins.auto_design.services.ga_run import GAContext, run_ga
from src.plugins.auto_design.services.population import ROLE_LABELS, ROLES
from src.plugins.auto_design.services.run_monitor import RunCancelled
from src.plugins.auto_design.services.database_folder import (
    check_folder_usable,
    describe_folder,
)

logger = logging.getLogger(__name__)

class _RunWorker(QThread):
    """Runs the GA steps off the UI thread and forwards what the run
    reports (status lines, progress, generation numbers) as signals."""

    status = Signal(str)
    progress = Signal(float)
    generation = Signal(object)  # GenerationStats
    succeeded = Signal(object)  # GAContext
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, context: GAContext, parent: QWidget | None = None):
        super().__init__(parent)
        self._context = context

        monitor = context.monitor
        monitor.on_status = self.status.emit
        monitor.on_progress = self.progress.emit
        monitor.on_generation = self.generation.emit

    def run(self) -> None:
        try:
            run_ga(self._context)
        except RunCancelled:
            logger.info("The GA run was cancelled by the user")
            self.cancelled.emit()
            return
        except Exception as exc:
            logger.exception("The GA run failed")
            self.failed.emit(str(exc) or exc.__class__.__name__)
            return

        self.succeeded.emit(self._context)

class AutoDesignWizard(QStackedWidget):
    """Step 1: SAP2000 file  ->  Step 2: allowed sections  ->  Step 3: frame types
    ->  Step 4: GA settings  ->  run page (live progress; Cancel, then Back to the
    settings)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setObjectName("page")

        # Collected data
        self.sap_path: str | None = None
        self.sections: list[SectionPermission] | None = None
        self.frame_roles: dict[str, str] | None = None  # frame -> role, from the Frame types page
        self.params: AutoDesignParams | None = None
        self.sap = None  # SapClient, set once step 2 has loaded the model

        self.context: GAContext | None = None  # result of the last finished run
        self._run_context: GAContext | None = None  # the run in progress
        self._run_worker: _RunWorker | None = None

        self._sections_page: SectionsPage | None = None
        self._roles_page: FrameRolesPage | None = None
        self._ga_page: GASettingsPage | None = None
        self._run_page: RunPage | None = None

        self.file_page = AutoDesignPage()
        self.file_page.next_requested.connect(self._show_sections)
        self.addWidget(self.file_page)

    # -----------------------------------------------------------------
    # Step 1 -> 2
    # -----------------------------------------------------------------

    def _show_sections(self, sap_path: str) -> None:
        self.sap_path = sap_path

        page = self._sections_page

        # Going back and forth with the same file keeps the loaded model
        # and the user's choices; a different file starts over.
        if page is None or page.sap_path != sap_path:
            if page is not None:
                self.removeWidget(page)
                page.deleteLater()

            self.sections = None
            self.sap = None
            self._drop_roles_page()  # the frame types belong to the old file

            page = SectionsPage(sap_path)
            page.back_requested.connect(lambda: self.setCurrentWidget(self.file_page))
            page.next_requested.connect(self._on_sections_accepted)

            self._sections_page = page
            self.addWidget(page)
            self.setCurrentWidget(page)
            page.start_loading()
            return

        self.setCurrentWidget(page)

    def _drop_roles_page(self) -> None:
        if self._roles_page is not None:
            self.removeWidget(self._roles_page)
            self._roles_page.deleteLater()
            self._roles_page = None

        self.frame_roles = None

    # -----------------------------------------------------------------
    # Step 2 -> 3 (frame types)
    # -----------------------------------------------------------------

    def _on_sections_accepted(self, sections: list[SectionPermission]) -> None:
        self.sections = sections
        self.sap = self._sections_page.client if self._sections_page else None

        logger.info(
            "Sections accepted: %d total, %d column, %d beam, "
            "%d horizontal brace, %d vertical brace",
            len(sections),
            sum(s.allowedForColumn for s in sections),
            sum(s.allowedForBeam for s in sections),
            sum(s.allowedForHorizontalBrace for s in sections),
            sum(s.allowedForVerticalBrace for s in sections),
        )

        self._show_roles()

    def _show_roles(self) -> None:
        # Created once per reference file, so the types the user edited
        # survive Back / Next. The frame types do not depend on the sections.
        if self._roles_page is None:
            if self.sap is None or not self.sap_path:
                logger.error("Cannot show the Frame types page: no SAP2000 connection")
                return

            page = FrameRolesPage(self.sap_path, self.sap)
            page.back_requested.connect(self._back_to_sections)
            page.next_requested.connect(self._on_roles_accepted)

            self._roles_page = page
            self.addWidget(page)
            self.setCurrentWidget(page)
            page.start_loading()
            return

        self.setCurrentWidget(self._roles_page)

    def _back_to_sections(self) -> None:
        if self._sections_page is not None:
            self.setCurrentWidget(self._sections_page)

    # -----------------------------------------------------------------
    # Step 3 -> 4 (GA settings)
    # -----------------------------------------------------------------

    def _on_roles_accepted(self, roles: dict[str, str]) -> None:
        self.frame_roles = dict(roles)

        logger.info(
            "Frame types accepted: %d frames, %s",
            len(roles),
            ", ".join(
                f"{sum(r == role for r in roles.values())} {ROLE_LABELS[role].lower()}"
                for role in ROLES
            ),
        )

        self._show_ga_settings()

    def _show_ga_settings(self) -> None:
        # Created once, so the values typed by the user survive Back / Next.
        if self._ga_page is None:
            page = GASettingsPage(self.sap_path or "")
            page.back_requested.connect(self._back_to_roles)
            page.run_requested.connect(self._on_params_accepted)

            self._ga_page = page
            self.addWidget(page)

        # A different SAP2000 file changes the default database folder
        # (unless the user has already chosen one).
        self._ga_page.set_sap_path(self.sap_path or "")

        self.setCurrentWidget(self._ga_page)

    def _back_to_roles(self) -> None:
        if self._roles_page is not None:
            self.setCurrentWidget(self._roles_page)

    # -----------------------------------------------------------------
    # Step 4 -> run
    # -----------------------------------------------------------------

    def _on_params_accepted(self, params: AutoDesignParams) -> None:
        self.params = params

        logger.info(
            "GA settings accepted: pop=%d, tournament=%d, generations=%d, "
            "mutation=%.2f%%, penalty=%.3g, "
            "update seismic loads=%s, models folder=%s",
            params.popSize,
            params.tournamentSize,
            params.genSize,
            params.mutationPercent,
            params.penalizeLevel,
            params.updateSeismicLoads,
            params.modelsFolder,
        )

        if not self._confirm_database_folder(params):
            return

        self._start_run()

    def _confirm_database_folder(self, params: AutoDesignParams) -> bool:
        """Warn that the database folder is cleared at the start of the run."""

        problem = check_folder_usable(params.modelsFolder, self.sap_path or "")

        if problem:
            QMessageBox.warning(self, "Database folder", problem)
            return False

        state = describe_folder(params.modelsFolder)

        if state.itemCount == 0:
            return True

        text = (
            f"The database folder is not empty:\n\n{params.modelsFolder}\n\n"
            f"It contains {state.itemCount} item(s)"
        )

        if state.generationFolders:
            text += (
                f", including {state.generationFolders} Generation folder(s) "
                "of a previous run"
            )

        text += (
            ".\n\nEverything inside it will be permanently deleted when the run "
            "starts. Continue?"
        )

        answer = QMessageBox.warning(
            self,
            "Database folder",
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        return answer == QMessageBox.StandardButton.Yes

    def _ensure_run_page(self) -> RunPage:
        # Created once and reset for every run.
        if self._run_page is None:
            page = RunPage()
            page.cancel_requested.connect(self._on_cancel_requested)
            page.back_requested.connect(self._back_to_ga_settings)

            self._run_page = page
            self.addWidget(page)

        return self._run_page

    def _start_run(self) -> None:
        if self._run_worker is not None:
            return

        if (
            self.sap is None
            or self.sections is None
            or self.frame_roles is None
            or self.params is None
            or not self.sap_path
        ):
            logger.error("Cannot start the run: input data is missing")
            return

        context = GAContext(
            sap=self.sap,
            params=self.params,
            sections=list(self.sections),
            sapPath=self.sap_path,
            frameRoles=dict(self.frame_roles),
        )
        worker = _RunWorker(context, self)

        page = self._ensure_run_page()
        page.start(self.params.genSize)

        worker.status.connect(page.add_status)
        worker.progress.connect(page.set_progress)
        worker.generation.connect(page.add_generation)
        worker.succeeded.connect(self._on_run_succeeded)
        worker.failed.connect(self._on_run_failed)
        worker.cancelled.connect(self._on_run_cancelled)
        worker.finished.connect(worker.deleteLater)

        self._run_context = context
        self._run_worker = worker

        self.setCurrentWidget(page)
        worker.start()

    def _on_cancel_requested(self) -> None:
        if self._run_context is not None:
            self._run_context.monitor.cancel()

    def _back_to_ga_settings(self) -> None:
        # The run page only allows Back once the run has stopped.
        if self._run_worker is None and self._ga_page is not None:
            self.setCurrentWidget(self._ga_page)

    def _on_run_succeeded(self, context: GAContext) -> None:
        self._run_worker = None
        self._run_context = None
        self.context = context
        self.sections = context.sections  # now with materialType filled

        if self._run_page is not None:
            self._run_page.set_state(FINISHED)

    def _on_run_failed(self, error: str) -> None:
        self._run_worker = None
        self._run_context = None

        if self._run_page is not None:
            self._run_page.set_state(FAILED, error)

    def _on_run_cancelled(self) -> None:
        self._run_worker = None
        self._run_context = None

        if self._run_page is not None:
            self._run_page.set_state(CANCELLED)
