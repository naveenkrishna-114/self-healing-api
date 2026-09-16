"""
compatibility_demo.py — Schema compatibility rules and AI approval gate demo.
"""

from self_healing_api.compatibility import CompatibilityEngine, MappingRule
from self_healing_api.errors.exceptions import ApprovalRequiredError


def main() -> None:
    engine = CompatibilityEngine()

    # Manual mapping rule
    engine.add_rule(
        MappingRule(rule_id="r1", source_field="usr_id", target_field="user_id", action="rename")
    )
    raw_api_response = {"usr_id": 1001, "email": "user@example.com"}
    transformed = engine.transform(raw_api_response)
    print("Transformed response:", transformed)

    # AI-assisted mapping rule with human approval gate
    ai_rule = MappingRule(
        rule_id="r_ai", source_field="phone_num", target_field="phone", action="rename"
    )
    sug = engine.propose_ai_suggestion("sug-42", [ai_rule], confidence=0.97)

    # Trying to apply unapproved suggestion raises ApprovalRequiredError
    try:
        engine.apply_ai_suggestion("sug-42", {"phone_num": "+1-555-0199"})
    except ApprovalRequiredError as exc:
        print(f"\n[AI Gate Guarded] Suggestion {exc.suggestion_id} requires explicit approval.")

    # Operator approves suggestion
    engine.approve_suggestion("sug-42")
    approved_res = engine.apply_ai_suggestion("sug-42", {"phone_num": "+1-555-0199"})
    print("Transformed after approval:", approved_res)


if __name__ == "__main__":
    main()
