"""Public API for reproducible, local financial research datasets."""

from research_data_engine.analytics import calculate_analytics
from research_data_engine.config import PipelineConfig, ValidationConfig, load_config
from research_data_engine.pipeline import PipelineRun, ingest
from research_data_engine.queries import QueryEngine, load_prices
from research_data_engine.storage import read_snapshot
from research_data_engine.validation import ValidationResult, validate_prices

__version__ = "0.1.0"
__all__ = [
    "PipelineConfig",
    "PipelineRun",
    "QueryEngine",
    "ValidationConfig",
    "ValidationResult",
    "calculate_analytics",
    "ingest",
    "load_config",
    "load_prices",
    "read_snapshot",
    "validate_prices",
]
