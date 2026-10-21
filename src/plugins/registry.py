"""Registry for Structure Lab plugins."""
from __future__ import annotations

from src.plugins.auto_design.plugin import AutoDesignPlugin
from src.plugins.base import Plugin
from src.plugins.placeholder import PlaceholderPlugin
from src.plugins.sld_to_sap.plugin import SldToSapPlugin


# Release switch: while False, Auto Design is shown on Home and in the
# sidebar as a planned tool (opens the "Under development" page). The
# real plugin and all its code stay in the project; set True to bring
# it back.
AUTO_DESIGN_ENABLED = False

_plugins: list[Plugin] = []


def register_plugin(plugin: Plugin) -> None:
    """Register a plugin instance (plugins are unique by ``name``)."""
    if any(existing.name == plugin.name for existing in _plugins):
        return

    _plugins.append(plugin)


def load_plugins() -> list[Plugin]:
    """Return all registered plugins."""
    return list(_plugins)


def register_builtin_plugins() -> None:
    """Register every plugin shipped with Structure Lab in navigation order."""
    auto_design = AutoDesignPlugin()

    if AUTO_DESIGN_ENABLED:
        register_plugin(auto_design)
    else:
        # Same name, title, icon and description as the real plugin, so
        # it looks identical on Home, but it only opens a placeholder page.
        register_plugin(
            PlaceholderPlugin(
                name=auto_design.name,
                title=auto_design.title,
                icon=auto_design.icon,
                description=auto_design.description,
            )
        )

    register_plugin(SldToSapPlugin())

    register_plugin(
        PlaceholderPlugin(
            name="pdms_to_sap",
            title="PDMS to SAP",
            icon="pdms2sap.png",
            description="Automatic geometry modeling of the structure using PDMS model.",
        )
    )

    register_plugin(
        PlaceholderPlugin(
            name="auto_cps",
            title="Auto CPS",
            icon="auto_cps.png",
            description="Automatic CPS modeling and design.",
        )
    )