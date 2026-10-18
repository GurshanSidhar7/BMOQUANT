"""Strict declarative configuration; file paths are relative to the YAML file."""

import re
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from research_data_engine.exceptions import ConfigurationError

REQUIRED_COLUMNS = ("symbol", "date", "open", "high", "low", "close", "volume")
CANONICAL_COLUMNS = (*REQUIRED_COLUMNS, "source")
Policy = Literal["quarantine", "reject"]


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class InputConfig(StrictModel):
    path: Path
    format: Literal["csv"] = "csv"
    source: str = Field(default="user_csv", min_length=1)
    date_format: str = "%Y-%m-%d"

    @model_validator(mode="after")
    def nonblank(self) -> Self:
        if not self.source.strip() or not self.date_format.strip():
            raise ValueError("input.source and input.date_format must be nonblank")
        return self


class ValidationConfig(StrictModel):
    duplicate_policy: Policy = "quarantine"
    invalid_price_policy: Policy = "quarantine"
    missing_value_policy: Policy = "reject"
    malformed_value_policy: Policy = "quarantine"
    extreme_return_threshold: float = Field(default=0.25, gt=0, allow_inf_nan=False)
    volume_change_ratio: float = Field(default=10.0, gt=1, allow_inf_nan=False)
    stale_price_window: int = Field(default=5, ge=2)
    calendar: Literal["none", "weekdays"] = "none"

    def policy_for(self, category: str) -> Policy:
        return {
            "duplicate_key": self.duplicate_policy,
            "missing_value": self.missing_value_policy,
            "malformed_value": self.malformed_value_policy,
        }.get(category, self.invalid_price_policy)


class OutputConfig(StrictModel):
    path: Path
    format: Literal["parquet"] = "parquet"


class PipelineConfig(StrictModel):
    dataset: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$")
    input: InputConfig
    schema_mapping: dict[str, str] = Field(
        default_factory=lambda: {c: c for c in REQUIRED_COLUMNS}, alias="schema"
    )
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    output: OutputConfig

    @model_validator(mode="after")
    def check_mapping(self) -> Self:
        missing = set(REQUIRED_COLUMNS) - self.schema_mapping.keys()
        unknown = self.schema_mapping.keys() - set(CANONICAL_COLUMNS)
        incoming = [normalize_name(c) for c in self.schema_mapping.values()]
        if missing or unknown:
            raise ValueError(
                f"schema mapping: missing={sorted(missing)}, unknown={sorted(unknown)}"
            )
        if any(not c for c in incoming) or len(set(incoming)) != len(incoming):
            raise ValueError("schema mapping must use distinct, nonblank incoming column names")
        return self


def load_config(path: str | Path) -> PipelineConfig:
    """Load YAML safely, reject unknown fields, and resolve paths against the config file."""
    path = Path(path).resolve()
    try:
        config = PipelineConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError, ValidationError, ValueError) as exc:
        raise ConfigurationError(f"Cannot load configuration {path}: {exc}") from exc
    for section in (config.input, config.output):
        section.path = (path.parent / section.path).resolve()
    return config
