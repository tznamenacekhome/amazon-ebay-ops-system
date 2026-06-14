# AI_README.md

This file tells ChatGPT and Codex what to read first when discussing MBOP.

## Read Order

1. CURRENT_STATE.md
2. DECISIONS.md
3. KNOWN_ISSUES.md
4. ROADMAP.md
5. AGENTS.md
6. database_schema.md
7. business_rules.md
8. backend_architecture.md

## Rules

- Supabase is the operational source of truth.
- Python integrations write to Supabase.
- Next.js API routes own backend/business logic.
- React frontend renders backend-provided values.
- Frontend must not talk directly to Supabase.
- Frontend must not recalculate landed cost, inventory value, profitability, workflow status, or dashboard totals.
- Do not infer live operational state from documentation.
- For live data, use a future authenticated MBOP AI API only if available.
- Do not expose secrets, tokens, service role keys, raw marketplace payloads, or unrestricted logs.