# Sourcing Inventory Sell-Through Snooze

Date: 2026-08-04

## Purpose

Operators can hide valid sourcing opportunities when the ASIN is already sufficiently stocked or recently purchased. This is a business timing decision, not a negative matching signal.

## UI Behavior

- The Sourcing Workspace My Price column shows current Amazon inventory plus a separate `+N pipeline` line.
- Pipeline units are grouped from MBOP workflow state:
  - purchased/not received
  - received/not sent to Amazon
  - outbound to Amazon but not yet reflected in Amazon inventory
- Selected opportunities can be moved with `Wait for sell-through`.

## Snooze Rule

When `Wait for sell-through` is selected, MBOP stores the current owned unit baseline:

`owned units = in-stock units + pipeline units`

The opportunity is re-presented when at least 10% of that baseline has sold through. Because units are whole numbers, MBOP requires at least one unit of sell-through.

Example:

- Baseline at action time: 5 units
- Required sell-through: 1 unit
- Re-present when owned units are 4 or fewer

## Matching Safety

Inventory sell-through snoozes are recorded as `inventory_snoozed` operator actions and opportunity statuses. They are not inserted as negative matching-intelligence examples, because the operator is saying the opportunity is valid but not needed right now.

## Reprocessing Behavior

Future scoring treats inventory snoozes as ASIN-level holds. New and existing opportunities for the same ASIN remain `inventory_snoozed` until the current owned unit count is at or below the stored re-presentation threshold.
