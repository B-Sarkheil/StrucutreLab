"""Registry for Structure Lab plugins."""
from __future__ import annotations

from src.plugins.auto_design.plugin import AutoDesignPlugin
from src.plugins.base import Plugin
from src.plugins.placeholder import PlaceholderPlugin


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
    register_plugin(AutoDesignPlugin())

    register_plugin(
        PlaceholderPlugin(
            name="sld_to_sap",
            title="SLD to SAP",
            icon="sld2sap.png",
            description="Automatic loading of the structure using piping SLD.",
        )
    )

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
            icon="sld2sap.png",
            description="Automatic CPS modeling and design.",
        )
    )

    