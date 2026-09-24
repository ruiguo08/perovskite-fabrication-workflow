"""Typed business errors raised by application operations.

Application operations never raise HTTP exceptions: the HTTP boundary
(``web.routes``) maps these errors to status codes and response bodies.
Only expected business failures are expressed as these errors; unexpected
exceptions propagate untouched so they keep normal 500 handling and server
logging.
"""

from __future__ import annotations


class OperationError(Exception):
    """Base class for expected business failures inside an operation."""


class RecordNotFound(OperationError):
    """The referenced record does not exist, or the caller must not learn
    whether it exists (ownership isolation reports the same error)."""


class AccessDenied(OperationError, PermissionError):
    """The authenticated actor is not allowed to perform this operation.

    Also subclasses :class:`PermissionError` so handlers and delegates that
    historically caught ``PermissionError`` keep working while the codebase
    migrates to the typed errors.
    """


class InvalidInput(OperationError, ValueError):
    """The command violates input or domain validation rules.

    Also subclasses :class:`ValueError` so handlers and delegates that
    historically caught ``ValueError`` keep working while the codebase
    migrates to the typed errors.
    """


class StateConflict(OperationError):
    """The command conflicts with the current persistent state (reserved for
    APIs whose existing contract maps such conflicts to 409)."""
