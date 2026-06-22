# AI_README.md

This file tells ChatGPT and Codex what to read first when discussing MBOP.

## Read Order

1. `CURRENT_STATE.md`
2. `DECISIONS.md`
3. `KNOWN_ISSUES.md`
4. `ROADMAP.md`
5. `AGENTS.md`
6. `docs/database_schema.md`
7. `docs/business_rules.md`
8. `docs/backend_architecture.md`
9. `docs/aws/MBOP_AWS_DEPLOYMENT.md`
10. `docs/aws/MBOP_AWS_SCHEDULER_PLAN.md`
11. `docs/aws/MBOP_AWS_OPERATIONS_RUNBOOK.md`
12. `docs/supabase_capacity.md`

## AWS Context

The authoritative AWS deployment and scheduler docs are under `docs/aws/`.
Read them before discussing cloud deployment, cost, Cognito/ALB auth,
EasyPost webhook routing, EventBridge schedules, ECS task definitions, WAF,
Secrets Manager, or production scheduler telemetry.

Historical AWS planning notes remain in `docs/cloud_deployment_phase1.md`,
`docs/aws_scheduler_task_plan.md`, and
`docs/chatgpt_handoff_to_codex_aws_deployment.md`. Use those only for
background; prefer the `docs/aws/` files for current state and operations.

## Rules

- Supabase is the operational source of truth.
- Python integrations write to Supabase.
- Next.js API routes own backend/business logic.
- React frontend renders backend-provided values.
- Frontend must not talk directly to Supabase.
- Frontend must not recalculate landed cost, inventory value, profitability, workflow status, or dashboard totals.
- Do not infer live operational state from documentation.
- For AWS state, inspect live AWS when current configuration matters; docs are
  an orientation layer, not the source of truth.
- For live data, use a future authenticated MBOP AI API only if available.
- Do not expose secrets, tokens, service role keys, raw marketplace payloads, or unrestricted logs.
