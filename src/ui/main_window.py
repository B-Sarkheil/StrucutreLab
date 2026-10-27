"""Main Structure Lab window."""
 
import logging
 
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..plugins.registry import load_plugins
from .home_page import HomePage
from .theme import LOGO_ICO
from .widgets import FadeStackedWidget
from .about_page import AboutPage
from .navigation import ABOUT_PAGE, HOME_PAGE, Navigation
from ..core import release_notes
from .release_notes_dialog import ReleaseNotesDialog

 
logger = logging.getLogger(__name__)
 
 
class TitleBar(QFrame):
    """Custom modern title bar."""
 
    def __init__(self, parent=None):
        super().__init__(parent)
 
        self.window = parent
        self.drag_position = None
 
        self.setObjectName("titleBar")
        self.setFixedHeight(42)
 
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(0)
 
        # ---------------------------------------------------------
        # Application identity
        # ---------------------------------------------------------
 
        logo = QLabel()
        logo.setObjectName("titleBarLogo")
        logo.setFixedSize(22, 22)

        logo_pixmap = QIcon(str(LOGO_ICO)).pixmap(QSize(22, 22))

        if logo_pixmap.isNull():
            logo.setText("◈")  # fallback if the icon file is missing
        else:
            logo.setPixmap(logo_pixmap)
 
        title = QLabel("Structure Lab")
        title.setObjectName("titleBarTitle")
 
        layout.addWidget(logo)
        layout.addSpacing(8)
        layout.addWidget(title)
        layout.addStretch()
 
        # ---------------------------------------------------------
        # Window controls
        # ---------------------------------------------------------
 
        self.minimize_button = self.create_button(
            "—",
            "titleBarMinimize",
        )
 
        self.maximize_button = self.create_button(
            "□",
            "titleBarMaximize",
        )
 
        self.close_button = self.create_button(
            "×",
            "titleBarClose",
        )
 
        self.minimize_button.clicked.connect(
            self.window.showMinimized
        )
 
        self.maximize_button.clicked.connect(
            self.toggle_maximize
        )
 
        self.close_button.clicked.connect(
            self.window.close
        )
 
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)
 
    @staticmethod
    def create_button(
        text: str,
        object_name: str,
    ) -> QPushButton:
        """Create a title-bar control button."""
 
        button = QPushButton(text)
        button.setObjectName(object_name)
        button.setFixedSize(42, 32)
        button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
 
        return button
 
    def toggle_maximize(self) -> None:
        """Toggle between maximized and normal window state."""
 
        if self.window.isMaximized():
            self.window.showNormal()
            self.maximize_button.setText("□")
        else:
            self.window.showMaximized()
            self.maximize_button.setText("❐")
 
    def mousePressEvent(self, event):
        """Start dragging the window."""
 
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = (
                event.globalPosition().toPoint()
                - self.window.frameGeometry().topLeft()
            )
 
            event.accept()
 
    def mouseMoveEvent(self, event):
        """Move the window while dragging."""
 
        if (
            event.buttons()
            & Qt.MouseButton.LeftButton
            and self.drag_position is not None
        ):
            self.window.move(
                event.globalPosition().toPoint()
                - self.drag_position
            )
 
            event.accept()
 
    def mouseDoubleClickEvent(self, event):
        """Maximize or restore on double-click."""
 
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximize()
 
            event.accept()
 
 
class MainWindow(QMainWindow):
    """Main application window.
 
    The window is a shell: title bar, navigation and a stack of pages.
    The Home page is built up front; each plugin page is created lazily
    the first time the user opens it.
    """
 
    def __init__(self, version: str):
        super().__init__()
        self._version = version
 
        # ---------------------------------------------------------
        # Plugins and pages
        # ---------------------------------------------------------
 
        self._plugins = {plugin.name: plugin for plugin in load_plugins()}
        self._pages: dict[str, QWidget] = {}
        self._current_key = HOME_PAGE
 
        # ---------------------------------------------------------
        # Frameless modern window
        # ---------------------------------------------------------
 
        self.setWindowTitle("Structure Lab")
        self.setWindowIcon(QIcon(str(LOGO_ICO)))
 
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
        )
 
        self.resize(950, 620)
        self.setMinimumSize(900, 580)
 
        # ---------------------------------------------------------
        # Central widget
        # ---------------------------------------------------------
 
        central = QFrame()
        central.setObjectName("mainWindow")
 
        self.setCentralWidget(central)
 
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
 
        # ---------------------------------------------------------
        # Custom title bar
        # ---------------------------------------------------------
 
        self.title_bar = TitleBar(self)
 
        root.addWidget(self.title_bar)
 
        # ---------------------------------------------------------
        # Main body
        # ---------------------------------------------------------
 
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
 
        self.navigation = Navigation(
            version=version,
            plugins=list(self._plugins.values()),
        )
        self.navigation.page_requested.connect(self.show_page)
 
        # ---------------------------------------------------------
        # Main content: a stack of pages
        # ---------------------------------------------------------
 
        content = QFrame()
        content.setObjectName("content")
 
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
 
        self.pages = FadeStackedWidget()
        self.pages.setObjectName("pageStack")
        content_layout.addWidget(self.pages)
 
        home = HomePage(list(self._plugins.values()))
        home.plugin_requested.connect(self.show_page)
        self._add_page(HOME_PAGE, home)
 
        body.addWidget(self.navigation)
        body.addWidget(content, 1)
 
        root.addLayout(body)
 
        self.show_page(HOME_PAGE)
 
    def _add_page(self, key: str, page: QWidget) -> None:
        """Store `page` under `key` and add it to the stack."""
 
        self._pages[key] = page
        self.pages.addWidget(page)
 

    def _create_page(self, key: str) -> QWidget | None:
        """Build the page for `key`; return None if it cannot be built."""

        if key == ABOUT_PAGE:
            return AboutPage(version=self._version)

        plugin = self._plugins.get(key)

        if plugin is None:
            logger.error("Unknown page requested: %s", key)
            return None

        try:
            return plugin.create_widget()
        except Exception:
            logger.exception("Could not create the page of plugin '%s'", key)
            return None

    def show_page(self, key: str) -> None:
        """Show the page for `key`, creating it on first use."""

        page = self._pages.get(key)

        if page is None:
            page = self._create_page(key)

            if page is None:
                self.navigation.set_current(self._current_key)
                return

            self._add_page(key, page)

        self.pages.fade_to(page)
        self._current_key = key
        self.navigation.set_current(key)


    def show_release_notes_if_needed(self) -> None:
        """After an update: show what is new once, then remember it."""

        try:
            notes = release_notes.pending_notes(self._version)

            if notes:
                ReleaseNotesDialog(notes, self._version, parent=self).exec()
        except Exception:
            logger.exception("Could not show the release notes")
        finally:
            release_notes.mark_seen(self._version)