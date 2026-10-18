from src.__main__ import ping_app
from src.plugins.registry import load_plugins


def test_ping_app():
    assert ping_app() is True


def test_load_plugins_returns_list():
    assert isinstance(load_plugins(), list)
