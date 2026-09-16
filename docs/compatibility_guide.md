# API Compatibility & AI Approval Guide

## Overview

The API Compatibility Layer allows applications to gracefully handle schema drift, field renames, and type conversions when upstream API services evolve.

## Safety & Non-Bypassable Approval Gate

1. **Rule Validation**: Every `MappingRule` must pass structural validation before it can be added to the engine.
2. **AI Approval Gate**: AI-generated mapping suggestions are stored in a pending state (`approved=False`).
3. Calling `apply_ai_suggestion()` on an unapproved suggestion raises `ApprovalRequiredError`.
4. Only after explicit developer approval via `approve_suggestion(suggestion_id)` will the engine transform payloads using the AI suggested rules.

## Example

```python
from self_healing_api.compatibility import CompatibilityEngine, MappingRule

engine = CompatibilityEngine()
engine.add_rule(MappingRule(rule_id="r1", source_field="usr_id", target_field="user_id", action="rename"))
transformed = engine.transform({"usr_id": 42})
# {"user_id": 42}
```
