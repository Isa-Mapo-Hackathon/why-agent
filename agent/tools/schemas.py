"""Pydantic input/output models for all four agent tools.

These models serve two purposes:
1. LangGraph uses the input models to validate tool arguments from the LLM.
2. The output models give every tool a consistent shape — including error/hint
   fields so the agent can self-correct on the next turn without raising.
"""

from __future__ import annotations

import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------


class TimeWindow(BaseModel):
    """A half-open time interval [start, end)."""

    start: str = Field(description="Window start (inclusive). ISO date string, e.g. '2026-01-01'.")
    end: str = Field(description="Window end (exclusive). ISO date string, e.g. '2026-02-01'.")

    @field_validator("start", "end")
    @classmethod
    def _validate_iso_date(cls, v: str) -> str:
        try:
            datetime.date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"Expected ISO date string (YYYY-MM-DD), got {v!r}")
        return v


# ---------------------------------------------------------------------------
# run_sql
# ---------------------------------------------------------------------------


class RunSqlInput(BaseModel):
    query: str = Field(description="A read-only SELECT (or WITH … SELECT) statement.")
    max_rows: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum rows to return. Rows beyond this are silently dropped; check `truncated`.",
    )


class RunSqlOutput(BaseModel):
    rows: list[dict] = Field(description="Result rows as dicts keyed by column name.")
    truncated: bool = Field(description="True if the result was cut at max_rows.")
    row_count: int = Field(description="Number of rows actually returned.")
    execution_ms: float = Field(description="Query wall-clock time in milliseconds.")
    error: str | None = Field(
        default=None, description="One-line error message if the query failed."
    )
    hint: str | None = Field(default=None, description="What to try next when error is set.")


# ---------------------------------------------------------------------------
# inspect_schema
# ---------------------------------------------------------------------------


class InspectSchemaInput(BaseModel):
    table: str | None = Field(
        default=None,
        description=(
            "Table name to describe (cols, types, business meaning, joins). "
            "Omit to list all available tables and named metrics."
        ),
    )


class ColumnInfo(BaseModel):
    name: str
    type: str
    description: str


class TableSummary(BaseModel):
    name: str
    description: str
    grain: str
    columns: list[ColumnInfo]
    joins: list[str] = Field(default_factory=list)


class InspectSchemaOutput(BaseModel):
    tables: list[str] | None = Field(
        default=None, description="Available table names (returned when no table arg given)."
    )
    metrics: list[str] | None = Field(
        default=None, description="Named metric keys usable in compare_periods / decompose_metric."
    )
    dimensions: list[str] | None = Field(
        default=None, description="Named dimension keys usable in decompose_metric."
    )
    table: TableSummary | None = Field(
        default=None, description="Full table description (returned when table arg is given)."
    )
    error: str | None = None
    hint: str | None = None

    @model_validator(mode="after")
    def _require_payload_or_error(self) -> InspectSchemaOutput:
        if self.error is None:
            has_payload = (
                self.tables is not None
                or self.metrics is not None
                or self.dimensions is not None
                or self.table is not None
            )
            if not has_payload:
                raise ValueError(
                    "InspectSchemaOutput must set error or at least one payload field."
                )
        return self


# ---------------------------------------------------------------------------
# compare_periods
# ---------------------------------------------------------------------------


class ComparePeriodsInput(BaseModel):
    metric: str = Field(
        description=(
            "Named metric from the semantic layer (e.g. 'avg_price', 'new_nutrition_records'). "
            "Call inspect_schema with no args to see the full list."
        )
    )
    before: TimeWindow = Field(description="Baseline time window.")
    after: TimeWindow = Field(description="Comparison time window.")
    segment: dict | None = Field(
        default=None,
        description=(
            "Optional filter dict applied to both windows, e.g. {'store': 'WHOLE_FOODS'}. "
            "Keys must be dimension names from the semantic layer."
        ),
    )


class ComparePeriodsOutput(BaseModel):
    before_value: float | None = Field(description="Metric value in the before window.")
    after_value: float | None = Field(description="Metric value in the after window.")
    abs_delta: float | None = Field(description="after_value − before_value.")
    pct_delta: float | None = Field(
        description="Percentage change: (abs_delta / before_value) × 100. None if before_value is 0."
    )
    error: str | None = None
    hint: str | None = None


# ---------------------------------------------------------------------------
# decompose_metric
# ---------------------------------------------------------------------------


class DecomposeMetricInput(BaseModel):
    metric: str = Field(
        description=(
            "Named metric from the semantic layer. Must have a time_column in the semantic layer."
        )
    )
    dimensions: list[str] = Field(
        description=(
            "Dimension names to slice by (e.g. ['store', 'category']). "
            "Call inspect_schema with no args to see available dimensions."
        )
    )
    time_window: TimeWindow = Field(description="Window over which to compute the decomposition.")


class SliceResult(BaseModel):
    dimension: str = Field(description="Dimension name.")
    value: str = Field(description="Dimension value for this slice.")
    metric_value: float | None = Field(description="Metric value for this slice.")
    anomaly_score: float | None = Field(
        description="Deviation vs. baseline — higher means more anomalous."
    )


class DecomposeMetricOutput(BaseModel):
    slices: list[SliceResult] = Field(
        default_factory=list,
        description="Slices ranked by anomaly_score descending.",
    )
    error: str | None = None
    hint: str | None = None
