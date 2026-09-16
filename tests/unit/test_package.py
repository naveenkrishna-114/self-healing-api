"""
Smoke test — verifies the package can be imported and has correct metadata.
This test must pass from Phase 1 onwards.
"""
from __future__ import annotations

import pytest

import self_healing_api


@pytest.mark.unit
def test_package_importable() -> None:
    """The package must be importable without errors."""
    assert self_healing_api is not None


@pytest.mark.unit
def test_package_version_defined() -> None:
    """Package must expose a __version__ string."""
    assert hasattr(self_healing_api, "__version__")
    assert isinstance(self_healing_api.__version__, str)
    assert len(self_healing_api.__version__) > 0


@pytest.mark.unit
def test_package_version_format() -> None:
    """Version must follow semantic versioning (MAJOR.MINOR.PATCH)."""
    version = self_healing_api.__version__
    parts = version.split(".")
    assert len(parts) == 3, f"Expected 3 version parts, got: {version}"
    for part in parts:
        assert part.isdigit(), f"Version part '{part}' is not numeric"


@pytest.mark.unit
def test_package_license_defined() -> None:
    """Package must expose a __license__ attribute."""
    assert hasattr(self_healing_api, "__license__")
    assert self_healing_api.__license__ == "MIT"


@pytest.mark.unit
def test_package_author_defined() -> None:
    """Package must expose an __author__ attribute."""
    assert hasattr(self_healing_api, "__author__")
    assert isinstance(self_healing_api.__author__, str)
