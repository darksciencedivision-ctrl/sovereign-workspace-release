"""Base adapter contract + deterministic mock backend (Plan §9.8, §12.2)."""
from adapters.base.contract import (
    AdapterCapability,
    AdapterContext,
    BaseAdapter,
    NakedLaunchRefused,
)
from adapters.base.mock_backend import MockReasoningBackend

__all__ = [
    "AdapterCapability", "AdapterContext", "BaseAdapter", "NakedLaunchRefused",
    "MockReasoningBackend",
]
