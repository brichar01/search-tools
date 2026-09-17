"""Shared test helpers."""

import shutil
import warnings

import pytest


def require_program(name: str) -> str:
    """Skip the calling test with a warning where a program is not installed."""
    path = shutil.which(name)
    if path is None:
        warnings.warn(f"{name} is not installed, skipping", stacklevel=2)
        pytest.skip(f"{name} is not installed")
    return path
