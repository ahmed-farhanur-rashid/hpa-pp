"""Generic API response wrappers.

All HPA++ FastAPI services use these response models for consistency.
Every endpoint returns an ApiResponse — clients check 'success' first.
"""

from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import Field

from shared.base import TimestampedModel
from shared.enums import SimulatorStatus

T = TypeVar("T")
DataT = TypeVar("DataT")


def _utcnow_str() -> str:
    """ISO 8601 UTC timestamp string."""
    return datetime.now(timezone.utc).isoformat()


class ApiResponse(TimestampedModel, Generic[T]):
    """Standard API response wrapper for all HPA++ services.

    Usage:
        return ApiResponse(data=some_model)
        return ApiResponse(success=False, error="Deployment not found")

    The frontend always checks 'success' before accessing 'data'.
    """

    success: bool = Field(
        default=True,
        description="Whether the request succeeded",
    )
    data: T | None = Field(
        default=None,
        description="Response payload (None on error)",
    )
    error: str | None = Field(
        default=None,
        description="Error message (None on success)",
    )
    error_code: str | None = Field(
        default=None,
        description="Machine-readable error code for programmatic handling",
        examples=["DEPLOYMENT_NOT_FOUND", "INVALID_CONFIG", "SIM_NOT_RUNNING"],
    )
    timestamp_utc: str = Field(
        default_factory=_utcnow_str,
        description="Response timestamp in ISO 8601 UTC",
    )


class ErrorResponse(TimestampedModel):
    """Structured error response — returned on all 4xx/5xx.

    Separate from ApiResponse to avoid Pydantic type invariance
    issues with optional vs required fields.
    """

    success: bool = Field(
        default=False,
        description="Always False for error responses",
    )
    error: str = Field(
        default="",
        description="Human-readable error description",
    )
    error_code: str | None = Field(
        default=None,
        description="Machine-readable error code",
        examples=["DEPLOYMENT_NOT_FOUND", "INVALID_CONFIG"],
    )
    timestamp_utc: str = Field(
        default_factory=_utcnow_str,
        description="Error timestamp in ISO 8601 UTC",
    )


class SimulatorStatusResponse(TimestampedModel):
    """Current status of the simulation engine."""

    status: SimulatorStatus
    sim_name: str = ""
    tick_count: int = 0
    simulated_minutes_elapsed: float = 0.0
    uptime_seconds: float = 0.0


class PaginatedResponse(TimestampedModel, Generic[DataT]):
    """Paginated list response for endpoints returning collections.

    Supports cursor or offset-based pagination.
    """

    items: list[DataT] = Field(
        ...,
        description="List of items for the current page",
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total number of items across all pages",
    )
    page: int = Field(
        default=1,
        ge=1,
        description="Current page number (1-indexed)",
    )
    page_size: int = Field(
        default=50,
        ge=1,
        le=1000,
        description="Number of items per page",
    )
    has_next: bool = Field(
        default=False,
        description="Whether there are more pages",
    )
    next_cursor: str | None = Field(
        default=None,
        description="Cursor for the next page (None if no more pages)",
    )
