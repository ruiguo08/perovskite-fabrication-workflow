"""Perovskite Solar Cell Fabrication Workflow web application."""

from __future__ import annotations


def create_app(*args, **kwargs):
    """Import the FastAPI app factory lazily so pure helpers stay dependency-light."""

    from .app import create_app as _create_app

    return _create_app(*args, **kwargs)


__all__ = ["create_app"]
