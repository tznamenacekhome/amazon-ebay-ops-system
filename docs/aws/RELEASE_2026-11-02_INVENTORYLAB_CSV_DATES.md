# InventoryLab CSV purchase dates

InventoryLab rejected exported rows with `String '--' was not recognized as a
valid DateTime`. The FBA export reused the UI date formatter, whose missing-date
placeholder is `--`. It also used a two-digit year and converted date-only
values through the browser timezone.

The export now uses a separate formatter: valid calendar dates become
`MM/DD/YYYY`; absent/invalid dates become an empty CSV cell. It preserves the
calendar date across timezones and does not invent purchase dates. Display
placeholders in the app are unchanged. InventoryLab supports blank purchased
dates, with its purchase-date setting controlling default behavior:
https://inventorylab.threecolts.support/hc/en-us/articles/4408213874459-Inventory-Management-Settings

Focused regression checks cover unknown/invalid dates, leap years, full years,
and UTC, Los Angeles, and Honolulu. Deployment validation follows.
