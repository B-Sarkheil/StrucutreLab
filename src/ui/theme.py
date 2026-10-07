"""Application-wide UI theme.

Design language: a structural drawing sheet. Blue-tinted "blueprint ink"
surfaces, drafting-cyan linework, and one signal color (amber, like the
highlight of a selected member in an analysis program) reserved for
"this is active / focused". Titles use Bahnschrift (DIN-style engineering
lettering, ships with Windows 10+); everything else uses Segoe UI. If
Bahnschrift is missing, Qt falls back to the default font.
"""

from pathlib import Path
from string import Template

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


# =========================================================
# Design tokens (single source of truth for colors)
# =========================================================

INK = "#0A1424"
INK_DEEP = "#060D19"
INK_RAISED = "#101C30"
INK_HI = "#16263F"
HERO_BG = "#0D2142"

RULE = "#1F3352"
RULE_HI = "#31496E"

PAPER = "#E9F0F8"
STEEL = "#8FA6C2"
STEEL_DIM = "#6F86A3"

CYAN = "#5CC8F0"
AMBER = "#FFB224"
BLUE = "#1F6FB5"
DANGER = "#D64045"

FONT_TITLE = "Bahnschrift"
FONT_BODY = "Segoe UI"

ICONS_DIR = Path(__file__).parent / "assets" / "icons"
LOGO_ICO = ICONS_DIR / "logo.ico"
LOGO_PNG = ICONS_DIR / "logo.png"


STYLESHEET = Template("""
    /* =====================================================
       Global
       ===================================================== */

    QWidget {
        background: $ink;
        color: $paper;
        font-family: "$font_body";
        font-size: 10pt;
    }

    QMainWindow {
        background: $ink;
    }

    QFrame {
        background: transparent;
        border: none;
    }

    QFrame#mainWindow {
        background: $ink;
        border: 1px solid $rule;
    }

    QLabel {
        background: transparent;
        color: $paper;
    }

    QWidget#page,
    QStackedWidget#pageStack {
        background: transparent;
    }

    QScrollArea#homeScroll {
        background: transparent;
        border: none;
    }

    QScrollArea#homeScroll > QWidget > QWidget {
        background: transparent;
    }


    /* =====================================================
       Custom Title Bar
       ===================================================== */

    QFrame#titleBar {
        background: $ink_deep;
        border-bottom: 1px solid $rule;
    }

    QLabel#titleBarLogo {
        background: transparent;
        color: $cyan;
        font-size: 15px;
        font-weight: 600;
    }

    QLabel#titleBarTitle {
        background: transparent;
        color: $paper;
        font-family: "$font_title";
        font-size: 11.5pt;
        font-weight: 600;
    }

    QPushButton#titleBarMinimize,
    QPushButton#titleBarMaximize,
    QPushButton#titleBarClose {
        background: transparent;
        color: $steel;
        border: none;
        border-radius: 6px;
        font-family: "$font_body";
        font-size: 11pt;
        padding: 0;
    }

    QPushButton#titleBarMinimize:hover,
    QPushButton#titleBarMaximize:hover {
        background: $ink_hi;
        color: $paper;
    }

    QPushButton#titleBarClose:hover {
        background: $danger;
        color: #FFFFFF;
    }

    QPushButton#titleBarClose:pressed {
        background: #A93338;
    }


    /* =====================================================
       Sidebar
       ===================================================== */

    QWidget#sidebar {
        background-color: $ink_raised;
        border-right: 1px solid $rule;
    }

    QPushButton#navButton {
        background: transparent;
        border: 1px solid transparent;
        border-radius: 10px;
        padding: 0;
    }

    QPushButton#navButton:hover {
        background: $ink_hi;
    }

    QPushButton#navButton:pressed {
        background: $rule;
    }

    QPushButton#navButton:checked {
        background: $ink_hi;
        border: 1px solid $rule;
    }

    QLabel#navIcon {
        background: transparent;
        color: $steel_dim;
        font-size: 20px;
        font-weight: 400;
    }

    QPushButton#navButton:hover QLabel#navIcon {
        color: $paper;
    }

    QPushButton#navButton:checked QLabel#navIcon {
        color: $cyan;
    }

    QLabel#navTitle {
        background: transparent;
        color: $steel;
        font-size: 9.5pt;
        font-weight: 600;
    }

    QPushButton#navButton:hover QLabel#navTitle,
    QPushButton#navButton:checked QLabel#navTitle {
        color: $paper;
    }

    QPushButton#navButton[planned="true"] QLabel#navTitle {
        color: $steel_dim;
    }

    QPushButton#navButton[planned="true"]:hover QLabel#navTitle,
    QPushButton#navButton[planned="true"]:checked QLabel#navTitle {
        color: $paper;
    }


    /* =====================================================
       About Card
       ===================================================== */

    QFrame#aboutCard {
        background: transparent;
        border: 1px solid transparent;
        border-radius: 10px;
    }

    QFrame#aboutCard:hover {
        background: $ink_hi;
        border: 1px solid transparent;
    }

    QFrame#aboutCard:pressed {
        background: $rule;
        border: 1px solid transparent;
    }

    QLabel#aboutIcon {
        background: transparent;
        color: $steel_dim;
        font-size: 24px;
    }

    QFrame#aboutCard:hover QLabel#aboutIcon {
        color: $paper;
    }

    QLabel#aboutTitle {
        background: transparent;
        color: $steel;
        font-size: 9pt;
        font-weight: 600;
    }

    QFrame#aboutCard:hover QLabel#aboutTitle {
        color: $paper;
    }

    QLabel#aboutName {
        background: transparent;
        color: $paper;
        font-size: 9pt;
        font-weight: 600;
    }

    QLabel#aboutVersion {
        background: transparent;
        color: $steel_dim;
        font-size: 8pt;
    }


    /* =====================================================
       Main Content
       ===================================================== */

    QFrame#content {
        background: $ink;
    }

    QLabel#pageTitle {
        color: $paper;
        font-family: "$font_title";
        font-size: 26pt;
        font-weight: 600;
    }

    QLabel#pageSubtitle {
        color: $steel;
        font-size: 10.5pt;
    }

    QLabel#sectionTitle {
        color: $steel;
        font-family: "$font_title";
        font-size: 11pt;
        font-weight: 600;
    }


    /* =====================================================
       Home: hero, tool cards, planned rows
       ===================================================== */

    QLabel#heroTitle {
        color: $paper;
        font-family: "$font_title";
        font-size: 30pt;
        font-weight: 600;
    }

    QLabel#heroSubtitle {
        color: $steel;
        font-size: 10.5pt;
    }

    QLabel#pluginIcon {
        background: $hero_bg;
        color: $cyan;
        border: 1px solid $rule_hi;
        border-radius: 8px;
        font-size: 22pt;
    }

    QLabel#pluginTitle {
        color: $paper;
        font-family: "$font_title";
        font-size: 15pt;
        font-weight: 600;
    }

    QLabel#pluginDescription {
        color: $steel;
        font-size: 9.5pt;
    }

    QLabel#plannedIcon {
        color: $steel_dim;
        font-size: 14pt;
    }

    QLabel#plannedTitle {
        color: $steel;
        font-size: 10.5pt;
        font-weight: 600;
    }

    QLabel#plannedDescription {
        color: $steel_dim;
        font-size: 9pt;
    }

    QLabel#plannedBadge {
        color: $steel_dim;
        border: 1px solid $rule;
        border-radius: 4px;
        padding: 1px 7px;
        font-size: 8.5pt;
    }


    /* =====================================================
       Buttons
       ===================================================== */

    QPushButton {
        background: $ink_hi;
        color: $paper;
        border: 1px solid $rule;
        border-radius: 8px;
        padding: 8px 16px;
    }

    QPushButton:hover {
        background: $rule;
        border-color: $rule_hi;
    }

    QPushButton:pressed {
        background: $rule_hi;
    }

    QPushButton:focus {
        border-color: $amber;
    }

    QPushButton:disabled {
        color: $steel_dim;
        background: $ink_raised;
        border-color: $rule;
    }

    QPushButton#primaryButton {
        background: $blue;
        color: #FFFFFF;
        border: 1px solid #2F86D0;
        font-weight: 600;
    }

    QPushButton#primaryButton:hover {
        background: #2A7DC8;
    }

    QPushButton#primaryButton:pressed {
        background: #185C99;
    }


    /* =====================================================
       Inputs
       ===================================================== */

    QLineEdit,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox {
        background: $ink_raised;
        color: $paper;
        border: 1px solid $rule;
        border-radius: 6px;
        padding: 7px 9px;
        selection-background-color: $blue;
    }

    QLineEdit:hover,
    QComboBox:hover,
    QSpinBox:hover,
    QDoubleSpinBox:hover {
        border-color: $rule_hi;
    }

    QLineEdit:focus,
    QComboBox:focus,
    QSpinBox:focus,
    QDoubleSpinBox:focus {
        border: 1px solid $amber;
    }


    /* =====================================================
       Scrollbars
       ===================================================== */

    QScrollBar:vertical {
        background: transparent;
        width: 10px;
        margin: 2px;
    }

    QScrollBar::handle:vertical {
        background: $rule;
        border-radius: 4px;
        min-height: 30px;
    }

    QScrollBar::handle:vertical:hover {
        background: $rule_hi;
    }

    QScrollBar:horizontal {
        background: transparent;
        height: 10px;
        margin: 2px;
    }

    QScrollBar::handle:horizontal {
        background: $rule;
        border-radius: 4px;
        min-width: 30px;
    }

    QScrollBar::handle:horizontal:hover {
        background: $rule_hi;
    }

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical,
    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {
        height: 0px;
        width: 0px;
    }


    /* =====================================================
       Tooltips
       ===================================================== */

    QToolTip {
        background: $ink_hi;
        color: $paper;
        border: 1px solid $rule_hi;
        padding: 6px 8px;
    }
""")


def apply_theme(app: QApplication) -> None:
    """Apply the Structure Lab dark theme."""

    palette = QPalette()

    palette.setColor(QPalette.Window, QColor(INK))
    palette.setColor(QPalette.WindowText, QColor(PAPER))

    palette.setColor(QPalette.Base, QColor(INK_RAISED))
    palette.setColor(QPalette.AlternateBase, QColor(INK_HI))

    palette.setColor(QPalette.Text, QColor(PAPER))
    palette.setColor(QPalette.BrightText, QColor("#FFFFFF"))

    palette.setColor(QPalette.Button, QColor(INK_HI))
    palette.setColor(QPalette.ButtonText, QColor(PAPER))

    palette.setColor(QPalette.ToolTipBase, QColor(INK_HI))
    palette.setColor(QPalette.ToolTipText, QColor(PAPER))

    palette.setColor(QPalette.Highlight, QColor(BLUE))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))

    palette.setColor(QPalette.Link, QColor(CYAN))

    app.setPalette(palette)

    app.setStyle("Fusion")

    app.setStyleSheet(
        STYLESHEET.substitute(
            ink=INK,
            ink_deep=INK_DEEP,
            ink_raised=INK_RAISED,
            ink_hi=INK_HI,
            hero_bg=HERO_BG,
            rule=RULE,
            rule_hi=RULE_HI,
            paper=PAPER,
            steel=STEEL,
            steel_dim=STEEL_DIM,
            cyan=CYAN,
            amber=AMBER,
            blue=BLUE,
            danger=DANGER,
            font_title=FONT_TITLE,
            font_body=FONT_BODY,
        )
    )