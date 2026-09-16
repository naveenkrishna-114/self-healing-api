"""
compatibility — API schema compatibility layer and AI approval gates.
"""

from self_healing_api.compatibility.engine import (
    AISuggestion,
    CompatibilityEngine,
    MappingRule,
    SchemaDetector,
)

__all__ = [
    "AISuggestion",
    "CompatibilityEngine",
    "MappingRule",
    "SchemaDetector",
]
