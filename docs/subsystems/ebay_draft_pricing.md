# eBay Draft Search Link Sheet

Last updated: 2026-06-28

## Purpose

`integrations/price_ebay_draft_listings.py` supports manual eBay seller draft
research from the Google Sheet named `ebay drafts`.

The workflow is AI-assisted search-link generation:

- read the draft listing title from column `D`
- generate a compact eBay sold-search keyword phrase
- write that phrase to column `E` as a clickable eBay sold-search link
- leave pricing columns untouched

The script is intentionally read/write only against the spreadsheet. It does
not create, revise, publish, or otherwise write to eBay listings.

## Sheet

Default spreadsheet:

`https://docs.google.com/spreadsheets/d/1HIO1960IiDkrRz5ljlh0IIt199ilMxeMwYQO4A7Jto4/edit`

Default tab:

`Sheet1`

Expected columns:

- `D`: `Listing Title`
- `E`: `Optimized search term`
- `F`: manual pricing column, untouched by this script

Column `E` is written as a Google Sheets formula:

```text
=HYPERLINK("https://www.ebay.com/sch/i.html?...LH_Sold=1&LH_Complete=1...", "optimized terms")
```

## Access

The local script uses the repo's Google service-account credentials from
`GOOGLE_APPLICATION_CREDENTIALS`.

The sheet must be shared as Editor with:

`amazon-ebay-ops-sync@waypoints-1369.iam.gserviceaccount.com`

The Codex Google Drive connector may have access even when the local service
account does not, so always verify local script access with a dry run before
using `--apply`.

## Commands

Dry run the next rows:

```powershell
python integrations\price_ebay_draft_listings.py --limit 10
```

Apply to the next blank rows:

```powershell
python integrations\price_ebay_draft_listings.py --limit 25 --only-blank --apply
```

Process a larger batch:

```powershell
python integrations\price_ebay_draft_listings.py --limit 100 --only-blank --apply
```

Useful options:

- `--limit N`: maximum rows to process
- `--only-blank`: skip rows where column `E` is already filled
- `--start-row N`: first sheet row to consider; default is `2`
- `--apply`: write to the sheet; without this, the script is dry-run only
- `--ai-model MODEL`: override the OpenAI model; default is `gpt-4.1-mini`

## Pricing

The script does not suggest pricing.

Seller Hub Product Research / Terapeak has the sold-price and average-shipping
data that would be ideal for this workflow, but it is not exposed through the
standard seller APIs available to MBOP. References found during research point
to limited/partner-gated Marketplace Insights or Terapeak beta access rather
than normal seller API access.

Current expected behavior:

- column `E` is useful and should be populated by the script
- column `F` and other pricing fields are left for manual review
- pricing should be manually decided from the linked sold-search results

## Recent Run

On 2026-06-28, the script was simplified to search-link generation only because
the available eBay APIs do not provide reliable sold-comps pricing for this
workflow. Column `E` is the only scripted output; pricing columns remain manual.
