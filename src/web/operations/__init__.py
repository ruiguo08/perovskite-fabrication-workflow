"""Application operations: transaction-owning entry points for state changes.

An application operation owns, for one use case:

- operator authorization (role scope and experiment ownership);
- input and domain-rule validation;
- the transaction boundary and lock ordering;
- orchestration of the connection-level data functions in
  :mod:`web.repository`;
- the audit record written inside the same transaction.

Operations raise the typed errors from :mod:`web.operations.errors` and never
HTTP exceptions; ``web.routes`` maps them at the boundary. Data access lives
in the repository modules: every query, lock, and write runs on the single
connection the operation opened, so no data function can silently open its
own transaction or commit early.
"""

from .errors import (
    AccessDenied,
    InvalidInput,
    OperationError,
    RecordNotFound,
    StateConflict,
)

__all__ = [
    "AccessDenied",
    "InvalidInput",
    "OperationError",
    "RecordNotFound",
    "StateConflict",
]
