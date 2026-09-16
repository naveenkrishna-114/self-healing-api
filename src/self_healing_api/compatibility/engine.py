"""
engine.py — API Schema compatibility detection, transformation rules, and AI approval gate.

Enforces strict human-in-the-loop approval before AI-generated schema mapping rules take effect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from self_healing_api.errors.exceptions import (
    ApprovalRequiredError,
    MappingValidationError,
    SchemaMismatchError,
)


@dataclass
class MappingRule:
    """
    Schema adaptation rule for mapping legacy/migrated response fields.
    """

    rule_id: str
    source_field: str
    target_field: str
    action: Literal["rename", "default", "remove", "type_cast"] = "rename"
    default_value: Any = None
    target_type: str | None = None

    def validate(self) -> list[str]:
        """Validate rule parameters."""
        errors: list[str] = []
        if not self.rule_id:
            errors.append("rule_id cannot be empty")
        if self.action in ("rename", "remove", "type_cast") and not self.source_field:
            errors.append(f"source_field required for action {self.action!r}")
        if self.action in ("rename", "default") and not self.target_field:
            errors.append(f"target_field required for action {self.action!r}")
        return errors


@dataclass
class AISuggestion:
    """Pending or approved AI-suggested schema mapping."""

    suggestion_id: str
    rules: list[MappingRule] = field(default_factory=list)
    confidence: float = 0.95
    approved: bool = False


class SchemaDetector:
    """Inspects JSON payloads against expected key structures."""

    def detect_mismatches(
        self, payload: dict[str, Any], expected_fields: set[str]
    ) -> tuple[list[str], list[str]]:
        """Return (missing_fields, unexpected_fields)."""
        actual_fields = set(payload.keys())
        missing = sorted(expected_fields - actual_fields)
        unexpected = sorted(actual_fields - expected_fields)
        return missing, unexpected


class CompatibilityEngine:
    """
    Compatibility transformer and AI suggestion management.
    """

    def __init__(self) -> None:
        self._rules: list[MappingRule] = []
        self._suggestions: dict[str, AISuggestion] = {}
        self._detector = SchemaDetector()

    def add_rule(self, rule: MappingRule) -> None:
        """Add an approved mapping rule."""
        errors = rule.validate()
        if errors:
            raise MappingValidationError(
                f"MappingRule {rule.rule_id!r} failed validation: {'; '.join(errors)}",
                rule_id=rule.rule_id,
                validation_errors=errors,
            )
        self._rules.append(rule)

    def check_schema(self, payload: dict[str, Any], expected_fields: set[str]) -> None:
        """Check payload and raise SchemaMismatchError if fields differ."""
        missing, unexpected = self._detector.detect_mismatches(payload, expected_fields)
        if missing or unexpected:
            msg = (
                f"Schema mismatch: {len(missing)} missing field(s), "
                f"{len(unexpected)} unexpected field(s)."
            )
            raise SchemaMismatchError(
                msg,
                missing_fields=missing,
                unexpected_fields=unexpected,
            )

    def transform(self, data: dict[str, Any]) -> dict[str, Any]:
        """Apply active mapping rules to transform JSON payload."""
        result = dict(data)
        for rule in self._rules:
            if rule.action == "rename":
                if rule.source_field in result:
                    val = result.pop(rule.source_field)
                    result[rule.target_field] = val
            elif rule.action == "default":
                if rule.target_field not in result:
                    result[rule.target_field] = rule.default_value
            elif rule.action == "remove":
                result.pop(rule.source_field, None)
            elif rule.action == "type_cast":
                if rule.source_field in result:
                    raw = result[rule.source_field]
                    if rule.target_type == "int":
                        result[rule.source_field] = int(raw)
                    elif rule.target_type == "float":
                        result[rule.source_field] = float(raw)
                    elif rule.target_type == "str":
                        result[rule.source_field] = str(raw)
        return result

    def propose_ai_suggestion(
        self, suggestion_id: str, rules: list[MappingRule], confidence: float = 0.95
    ) -> AISuggestion:
        """Create a pending AI suggestion requiring human approval."""
        for rule in rules:
            errors = rule.validate()
            if errors:
                raise MappingValidationError(
                    f"AI MappingRule {rule.rule_id!r} failed validation: {'; '.join(errors)}",
                    rule_id=rule.rule_id,
                    validation_errors=errors,
                )

        sug = AISuggestion(
            suggestion_id=suggestion_id,
            rules=rules,
            confidence=confidence,
            approved=False,
        )
        self._suggestions[suggestion_id] = sug
        return sug

    def approve_suggestion(self, suggestion_id: str) -> None:
        """Approve an AI suggestion, converting its rules to active status."""
        if suggestion_id not in self._suggestions:
            raise ValueError(f"Suggestion {suggestion_id!r} not found.")

        sug = self._suggestions[suggestion_id]
        sug.approved = True
        for rule in sug.rules:
            self.add_rule(rule)

    def apply_ai_suggestion(self, suggestion_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Apply an AI suggestion to payload (raises ApprovalRequiredError if not approved)."""
        if suggestion_id not in self._suggestions:
            raise ValueError(f"Suggestion {suggestion_id!r} not found.")

        sug = self._suggestions[suggestion_id]
        if not sug.approved:
            raise ApprovalRequiredError(
                f"AI suggestion {suggestion_id!r} requires developer approval.",
                suggestion_id=suggestion_id,
                confidence=sug.confidence,
            )

        return self.transform(data)
