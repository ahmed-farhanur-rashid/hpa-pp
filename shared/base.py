"""Base models and mixins for all HPA++ Pydantic schemas.

Every shared model inherits from one of these base classes to ensure
consistent serialization, strict validation, and explicit unit conventions.

RULE 1.2 — All JSON payloads use snake_case.
RULE 1.3 — Every incoming payload must pass strict runtime validation.
"""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TimestampedModel(BaseModel):
    """Base model with strict validation — no extra fields, no coercion.

    All HPA++ data models MUST inherit from this or AuditModel.

    Configuration:
        populate_by_name=True — allow both alias and field name population
        extra="forbid" — reject unknown fields at every service boundary
        frozen=False — mutable for internal use; freeze per-service if needed
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        frozen=False,
        validate_assignment=True,
        validate_default=True,
    )


def _utcnow() -> datetime:
    """Return current UTC datetime with timezone awareness."""
    return datetime.now(timezone.utc)


class AuditModel(TimestampedModel):
    """Adds automatic UTC timestamp to every record.

    All database-persisted models should inherit from this.
    The timestamp_utc field is auto-set on creation.

    TODO: Consider adding updated_at_utc for mutable records.
    """

    timestamp_utc: datetime = Field(
        default_factory=_utcnow,
        description="Record creation timestamp (UTC, auto-set)",
        examples=["2026-07-22T14:30:00Z"],
    )
