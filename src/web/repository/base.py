"""Connection ownership and lifecycle shared by every domain mixin; WebRepository composes the domain mixins on top of this base."""

from __future__ import annotations

from ..database import Database

class WebRepositoryBase:
    """Owns the async database connection."""

    def __init__(self, database: Database) -> None:
        self.database = database
