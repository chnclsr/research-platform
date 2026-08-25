from importlib.metadata import version as distribution_version

from research_platform import VERSION, __version__
from research_platform.api import app as api_app
from research_platform.control_panel import app as control_panel_app


def test_runtime_surfaces_share_installed_package_version():
    expected = distribution_version("research-platform")

    assert VERSION == __version__ == expected
    assert api_app.version == control_panel_app.version == expected
