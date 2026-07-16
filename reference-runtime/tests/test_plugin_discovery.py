import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "nomad_sentinel", "runtime", "core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "nomad_sentinel", "runtime", "plugins"))

from plugin_registry import PluginRegistry


def test_real_discovery_finds_plugins_on_actual_filesystem_layout():
    """
    Every other test in this suite injects a fake/mock registry and never
    exercises PluginRegistry.discover() against the real directory layout.
    That's exactly how a wrong PLUGINS_DIR path went unnoticed: discovery
    silently found nothing, and nothing was checking. This test uses the
    real registry, unmocked, so a regression here fails loudly instead of
    quietly.
    """
    registry = PluginRegistry()
    loaded = registry.discover()

    assert "qwen_cloud" in loaded, (
        "qwen_cloud plugin was not discovered -- if this fails, check "
        "PLUGINS_DIR in plugin_registry.py actually points at "
        "runtime/plugins/, not runtime/core/plugins/"
    )
    assert "guardian" in loaded
    assert "llama_cpp" in loaded
