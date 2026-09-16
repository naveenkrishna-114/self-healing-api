"""Unit tests for CompatibilityEngine and AI Approval Gate."""

import pytest

from self_healing_api.compatibility import CompatibilityEngine, MappingRule, SchemaDetector
from self_healing_api.errors.exceptions import (
    ApprovalRequiredError,
    MappingValidationError,
)


@pytest.mark.unit
class TestCompatibilityEngine:
    def test_schema_detector_missing_and_unexpected(self) -> None:
        detector = SchemaDetector()
        payload = {"user_id": 1, "extra": "foo"}
        expected = {"user_id", "email"}
        missing, unexpected = detector.detect_mismatches(payload, expected)
        assert missing == ["email"]
        assert unexpected == ["extra"]

    def test_transform_rename_field(self) -> None:
        engine = CompatibilityEngine()
        rule = MappingRule(
            rule_id="r1", source_field="usr_id", target_field="user_id", action="rename"
        )
        engine.add_rule(rule)
        data = {"usr_id": 42, "name": "Alice"}
        transformed = engine.transform(data)
        assert transformed == {"user_id": 42, "name": "Alice"}

    def test_invalid_rule_raises_validation_error(self) -> None:
        engine = CompatibilityEngine()
        invalid_rule = MappingRule(rule_id="", source_field="", target_field="")
        with pytest.raises(MappingValidationError):
            engine.add_rule(invalid_rule)

    def test_ai_suggestion_approval_gate(self) -> None:
        engine = CompatibilityEngine()
        rule = MappingRule(
            rule_id="r2", source_field="old_val", target_field="new_val", action="rename"
        )
        _ = engine.propose_ai_suggestion("sug-1", [rule], confidence=0.98)

        # Before approval — applying raises ApprovalRequiredError
        with pytest.raises(ApprovalRequiredError) as exc_info:
            engine.apply_ai_suggestion("sug-1", {"old_val": "test"})
        assert exc_info.value.suggestion_id == "sug-1"
        assert exc_info.value.confidence == 0.98

        # Explicit approval
        engine.approve_suggestion("sug-1")

        # After approval — transformation succeeds
        result = engine.apply_ai_suggestion("sug-1", {"old_val": "test"})
        assert result == {"new_val": "test"}

    def test_actions_default_remove_and_type_cast(self) -> None:
        from self_healing_api.errors.exceptions import SchemaMismatchError

        engine = CompatibilityEngine()
        engine.add_rule(MappingRule("r_def", "", "country", action="default", default_value="US"))
        engine.add_rule(MappingRule("r_rem", "internal_secret", "", action="remove"))
        engine.add_rule(MappingRule("r_cast", "age", "", action="type_cast", target_type="int"))

        payload = {"name": "Bob", "internal_secret": "xyz", "age": "25"}
        res = engine.transform(payload)
        assert res["country"] == "US"
        assert "internal_secret" not in res
        assert res["age"] == 25

        with pytest.raises(SchemaMismatchError):
            engine.check_schema(res, expected_fields={"name", "age", "country", "missing_field"})

    def test_suggestion_not_found_raises_value_error(self) -> None:
        engine = CompatibilityEngine()
        with pytest.raises(ValueError, match="not found"):
            engine.approve_suggestion("unknown-sug")
        with pytest.raises(ValueError, match="not found"):
            engine.apply_ai_suggestion("unknown-sug", {})

    def test_schema_match_no_error(self) -> None:
        engine = CompatibilityEngine()
        engine.check_schema({"id": 1, "name": "test"}, {"id", "name"})  # does not raise

    def test_transform_edge_cases(self) -> None:
        engine = CompatibilityEngine()
        # rename when field is absent
        engine.add_rule(MappingRule(
            rule_id="r1", source_field="absent", target_field="target", action="rename"
        ))
        # default when target is already present
        engine.add_rule(MappingRule(
            rule_id="r2",
            source_field="",
            target_field="existing",
            default_value="new",
            action="default",
        ))
        # type_cast when field is absent
        engine.add_rule(MappingRule(
            rule_id="r3",
            source_field="absent2",
            target_field="",
            action="type_cast",
            target_type="int",
        ))
        # type_cast to float and str
        engine.add_rule(MappingRule(
            rule_id="r4",
            source_field="num_str",
            target_field="",
            action="type_cast",
            target_type="float",
        ))
        engine.add_rule(MappingRule(
            rule_id="r5",
            source_field="num_val",
            target_field="",
            action="type_cast",
            target_type="str",
        ))
        # remove action
        engine.add_rule(MappingRule(
            rule_id="r6",
            source_field="to_remove",
            target_field="",
            action="remove",
        ))
        # type cast with unsupported type or custom action
        custom_rule = MappingRule(
            rule_id="r7",
            source_field="dummy",
            target_field="",
            action="type_cast",
            target_type="unsupported",
        )
        engine._rules.append(custom_rule)
        noop_rule = MappingRule(
            rule_id="r8",
            source_field="dummy",
            target_field="",
            action="noop",  # type: ignore[arg-type]
        )
        engine._rules.append(noop_rule)

        res = engine.transform({
            "existing": "orig",
            "num_str": "3.14",
            "num_val": 42,
            "to_remove": "bye",
            "dummy": "val",
        })
        assert res["existing"] == "orig"
        assert res["num_str"] == 3.14
        assert res["num_val"] == "42"
        assert "to_remove" not in res
        assert res["dummy"] == "val"

    def test_propose_ai_suggestion_validation_failure(self) -> None:
        from self_healing_api.errors.exceptions import MappingValidationError

        engine = CompatibilityEngine()
        # Invalid rule missing rule_id
        invalid_rule = MappingRule(rule_id="", source_field="s", target_field="t", action="rename")
        with pytest.raises(MappingValidationError):
            engine.propose_ai_suggestion("sug-invalid", [invalid_rule])
