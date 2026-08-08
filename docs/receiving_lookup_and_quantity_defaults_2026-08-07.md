# Receiving Lookup and Quantity Defaults - 2026-08-07

## Context

Two receiving issues surfaced while processing multi-package and damaged-label
eBay orders:

- eBay can provide multiple tracking numbers without a per-package quantity
  allocation. MBOP knew the total order quantity, but the package-level expected
  quantity was null.
- Torn or incomplete labels made it difficult to find the remaining package
  when only the eBay order number or the last digits of the tracking number
  were available.

The Keepa catalog cycle drawer also had a pending display-only update so short
cycle display names can be shown without losing the full cycle id in the title.

## Changes

### Receiving package quantity display

- Unknown package quantities no longer default to `0` in the receiving drawer.
- The drawer now shows `Expected remaining` using the remaining purchase item
  quantity when `quantity_expected_in_package` is null.
- The default quantity received draft uses the same expected-remaining helper as
  validation and save payload generation.

This keeps multi-package receiving aligned with the operator workflow:

1. Show the total remaining quantity when the package allocation is unknown.
2. Let the operator adjust the quantity received to what is physically in that
   package.
3. Let the existing split logic reduce the remaining item quantity for later
   packages.

### Receiving search and scan lookup

- The receiving page now asks the server for matches when the input is:
  - a likely full tracking number,
  - an eBay order number such as `15-14964-83654`,
  - or a numeric tracking suffix from 6 to 11 digits.
- The receiving API now supports scan lookup by:
  - exact eBay order number,
  - normalized tracking candidates,
  - and trailing numeric tracking suffix.
- Server lookup still only returns open, delivered package links whose purchase
  item is not in a closed receiving state.
- Duplicate rows are deduped by package link/item identity before returning.

This allows operators to find a package even when the barcode is damaged or the
package split item has stale item-level tracking while the package link itself
has the correct tracking number.

### Keepa catalog cycle drawer

- The dashboard scheduler drawer now displays `cycle.displayName` when present.
- The full cycle id remains available as the table cell title.
- When no display name is available, the UI still falls back to the shortened
  cycle id.

## Validation

- `npm run build` passed after the receiving changes.
- Direct Supabase verification confirmed order `15-14964-83654` and tracking
  suffix `207505` both resolve to the same remaining open package row for
  tracking `875245207505`.

