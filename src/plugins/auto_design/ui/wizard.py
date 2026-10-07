"""Auto Design wizard: the container that moves between the plugin's pages."""
from __future__ import annotations

import logging

from PySide6.QtWidgets import QStackedWidget, QWidget

from src.plugins.auto_design.params import AutoDesignParams, SectionPermission
from src.plugins.auto_design.ui.page import AutoDesignPage
from src.plugins.auto_design.ui.sections_page import SectionsPage

logger = logging.getLogger(__name__)


class AutoDesignWizard(QStackedWidget):
    """Step 1: GA settings  ->  Step 2: allowed sections  ->  (next steps)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setObjectName("page")

        # Collected data
        self.params: AutoDesignParams | None = None
        self.sections: list[SectionPermission] | None = None
        self.sap = None  # SapClient, set once step 2 has loaded the model

        self._sections_page: SectionsPage | None = None

        self.form_page = AutoDesignPage()
        self.form_page.next_requested.connect(self._show_sections)
        self.addWidget(self.form_page)

    def _show_sections(self, params: AutoDesignParams) -> None:
        self.params = params

        page = self._sections_page

        # Going back and forth with the same file keeps the loaded model
        # and the user's choices; a different file starts over.
        if page is None or page.sap_path != params.sapPath:
            if page is not None:
                self.removeWidget(page)
                page.deleteLater()

            page = SectionsPage(params.sapPath)
            page.back_requested.connect(lambda: self.setCurrentWidget(self.form_page))
            page.next_requested.connect(self._on_sections_accepted)

            self._sections_page = page
            self.addWidget(page)
            self.setCurrentWidget(page)
            page.start_loading()
            return

        self.setCurrentWidget(page)

    def _on_sections_accepted(self, sections: list[SectionPermission]) -> None:
        self.sections = sections
        self.sap = self._sections_page.client if self._sections_page else None

        logger.info(
            "Sections accepted: %d total, %d column, %d beam, %d brace",
            len(sections),
            sum(s.allowedForColumn for s in sections),
            sum(s.allowedForBeam for s in sections),
            sum(s.allowedForBrace for s in sections),
        )

        # TODO: open the next page of the wizard.
