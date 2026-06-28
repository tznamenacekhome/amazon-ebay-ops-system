# Architecture Index

Status: Phase A final
Last updated: 2026-06-27

## Purpose

This directory is the starting point for MBOP architecture work, especially the
MBOP / ZFI boundary.

Future developers and Codex sessions should begin here before changing finance,
inventory value, dashboard, integration, or cross-system behavior.

## Where To Start

Start with these documents in this order:

1. [SYSTEM_BOUNDARIES.md](./SYSTEM_BOUNDARIES.md)
   Defines ownership. Read this first to understand what MBOP owns, what ZFI
   owns, what is temporary, and what must never cross the boundary.

2. [DATA_FLOW.md](./DATA_FLOW.md)
   Defines how data moves. Use this to decide whether a dataset is an ongoing
   MBOP-to-ZFI summary, a one-time migration, ZFI-only data, or future scoped
   drilldown.

3. [INTEGRATION_PRINCIPLES.md](./INTEGRATION_PRINCIPLES.md)
   Defines integration rules. Use this before implementing any feature that
   touches MBOP/ZFI, YNAB, Amazon cash/payouts, business value, tax, or Ask
   Zoltar drilldown.

Then check the repo-level documents:

- [DECISIONS.md](../../DECISIONS.md)
  Permanent architecture decisions. Use this to understand why the current
  boundary exists and what decisions should not be casually reopened.

- [ROADMAP.md](../../ROADMAP.md)
  Future work. Use this to place new work in the right phase without changing
  stable architecture.

- Feature PRDs in [docs](../)
  Functional requirements. Use PRDs to understand desired behavior after the
  ownership and data-flow boundary is clear.

## Working Rule

If a new feature cannot clearly answer the review questions in
[INTEGRATION_PRINCIPLES.md](./INTEGRATION_PRINCIPLES.md), stop implementation
and update architecture documentation first.

Do not use implementation work to quietly redefine ownership.
