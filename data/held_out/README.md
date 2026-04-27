# Held-Out Eval Data

Reserved synthetic cases for deterministic evaluation. The project runs held-out
evals on these files to detect routing or grounding regressions.

Expected fields match the seed schema and include:

- `expected_route`
- `expected_approval_required`
- `expected_key_risk_labels`
- `expected_task_owner_category`
- `scenario_summary`
