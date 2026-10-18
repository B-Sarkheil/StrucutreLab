"""Auto Design wizard: the container that moves between the plugin's pages."""
from __future__ import annotations

import logging

from PySide6.QtWidgets import QStackedWidget, QWidget

from src.plugins.auto_design.params import AutoDesignParams, SectionPermission
from src.plugins.auto_design.ui.ga_settings_page import GASettingsPage
from src.plugins.auto_design.ui.page import AutoDesignPage
from src.plugins.auto_design.ui.sections_page import SectionsPage

logger = logging.getLogger(__name__)


class AutoDesignWizard(QStackedWidget):
    """Step 1: SAP2000 file  ->  Step 2: allowed sections  ->  Step 3: GA settings."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setObjectName("page")

        # Collected data
        self.sap_path: str | None = None
        self.sections: list[SectionPermission] | None = None
        self.params: AutoDesignParams | None = None
        self.sap = None  # SapClient, set once step 2 has loaded the model

        self._sections_page: SectionsPage | None = None
        self._ga_page: GASettingsPage | None = None

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

            page = SectionsPage(sap_path)
            page.back_requested.connect(lambda: self.setCurrentWidget(self.file_page))
            page.next_requested.connect(self._on_sections_accepted)

            self._sections_page = page
            self.addWidget(page)
            self.setCurrentWidget(page)
            page.start_loading()
            return

        self.setCurrentWidget(page)

    # -----------------------------------------------------------------
    # Step 2 -> 3
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

        self._show_ga_settings()

    def _show_ga_settings(self) -> None:
        # Created once, so the values typed by the user survive Back / Next.
        if self._ga_page is None:
            page = GASettingsPage()
            page.back_requested.connect(self._back_to_sections)
            page.next_requested.connect(self._on_params_accepted)

            self._ga_page = page
            self.addWidget(page)

        self.setCurrentWidget(self._ga_page)

    def _back_to_sections(self) -> None:
        if self._sections_page is not None:
            self.setCurrentWidget(self._sections_page)

    # -----------------------------------------------------------------
    # Step 3 -> next
    # -----------------------------------------------------------------

    def _on_params_accepted(self, params: AutoDesignParams) -> None:
        self.params = params

        logger.info(
            "GA settings accepted: pop=%d, tournament=%d, generations=%d, "
            "mutation=%.2f%%, penalty=%.3g, tolerance=%.3g cm",
            params.popSize,
            params.tournamentSize,
            params.genSize,
            params.mutationPercent,
            params.penalizeLevel,
            params.tolerance,
        )

        # TODO: open the next page of the wizard.