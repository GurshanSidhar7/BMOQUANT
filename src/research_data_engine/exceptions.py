"""Actionable failures exposed by the public API and CLI."""


class ResearchDataError(Exception):
    """Base exception for expected application failures."""


class ConfigurationError(ResearchDataError):
    """Configuration could not be loaded or violates the contract."""


class IngestionError(ResearchDataError):
    """Input files cannot be discovered, scanned, or normalized."""


class DataValidationError(ResearchDataError):
    """A dataset is rejected; a previous published snapshot remains active."""


class StorageError(ResearchDataError):
    """A snapshot could not be read or safely published."""


class QueryError(ResearchDataError):
    """An analytical query is invalid or is not a single SELECT statement."""


class BenchmarkError(ResearchDataError):
    """A benchmark failed or produced nonequivalent mathematical results."""
