# Seed Cases

This folder stores synthetic intake cases for deterministic end-to-end demos.

Expected fields per case:

- `case_id`
- `customer_name`
- `account_name`
- `submitted_at` (ISO timestamp)
- `intake_email_text`
- `contract_text`
- `order_form_text`
- `implementation_notes`
- `security_questionnaire_text`
- `metadata` (optional object)
- `expected_route` (one of `auto_approve`, `legal`, `security`, `implementation`, `finance`)
- `expected_approval_required` (boolean)
- `expected_key_risk_labels` (list)
- `expected_task_owner_category` (string)
- `scenario_summary` (short description)

Validation uses these files directly from `data/seed/cases/*.json`.
