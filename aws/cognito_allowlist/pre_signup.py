"""Cognito pre-signup allowlist for MBOP Google auth."""

from __future__ import annotations

import os


def _allowed_emails() -> set[str]:
    raw = os.environ.get("MBOP_ALLOWED_EMAILS", "")
    return {
        email.strip().lower()
        for email in raw.replace(";", ",").split(",")
        if email.strip()
    }


def lambda_handler(event, _context):
    attributes = event.get("request", {}).get("userAttributes", {}) or {}
    email = str(attributes.get("email") or "").strip().lower()

    if not email:
        raise Exception("MBOP access denied: Google account did not provide an email address.")

    if email not in _allowed_emails():
        raise Exception("MBOP access denied: this Google email is not on the MBOP allowlist.")

    return event
