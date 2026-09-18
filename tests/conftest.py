"""Shared test helpers."""

import shutil
import warnings

import pytest


def require_model(name: str):
    """Skip the calling test with a warning where the model cannot be loaded."""
    try:
        from model2vec import StaticModel

        return StaticModel.from_pretrained(name)
    except (ImportError, OSError) as error:
        warnings.warn(f"{name} is unavailable ({error}), skipping", stacklevel=2)
        pytest.skip(f"{name} is unavailable")


def require_program(name: str) -> str:
    """Skip the calling test with a warning where a program is not installed."""
    path = shutil.which(name)
    if path is None:
        warnings.warn(f"{name} is not installed, skipping", stacklevel=2)
        pytest.skip(f"{name} is not installed")
    return path
