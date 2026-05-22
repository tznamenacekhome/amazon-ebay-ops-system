# Matching Engine

# Purpose

The matching engine enriches purchase_items using RevSeller Google Sheet data.

Primary goals:
- assign ASINs
- assign target sell prices
- minimize incorrect matches
- support future automation

---

# Core Rules

## Video Games Are Platform-Specific

Never auto-match across systems.

Examples:
- Minecraft PS4 != Minecraft Switch
- Madden Xbox != Madden PS5

---

# Current Matching Rules

## Preferred Match

Match:
- normalized title
- normalized system
