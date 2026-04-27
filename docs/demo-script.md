# AI FlowOps Demo Script

Use this exact flow for reviewer walkthroughs.

1. Open a terminal in `C:\dev\ai-flowops`.
2. Run a clean setup:
   `python scripts/demo_reset.py`
3. Start the app:
   `uvicorn app.main:app --reload`
4. Open `http://127.0.0.1:8000`.
5. On the dashboard (`/`), confirm seeded cases and KPI summary.
6. Open `/cases` and inspect a clean case.
7. Open `/cases` and inspect a legal or security case.
8. If an approval case is present, open `/approvals` and action approve or override.
9. Open the corresponding `/cases/{case_id}` page to review:
   - evidence,
   - findings,
   - routing decision,
   - trace timeline.
10. Open `/evals` to review held-out eval pass/fail.
11. Open `/kpis` and confirm route counts / escalation stats.
12. Open `/playbook` to review deterministic routing policy.

The demo intentionally prioritizes inspectability over bells and whistles. The strongest signal is deterministic governance with clear traces, not visual decoration.
