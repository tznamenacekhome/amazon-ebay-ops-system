from __future__ import annotations

import base64
import datetime as dt
import os
from dataclasses import dataclass
from typing import Any

import requests

from sourcing_common import required_env


EBAY_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_RATE_LIMIT_URL = "https://api.ebay.com/developer/analytics/v1_beta/rate_limit/"
EBAY_BROWSE_RESOURCE = "buy.browse"


@dataclass(frozen=True)
class EbayBrowseQuota:
    resource: str
    limit: int
    count: int
    remaining: int
    reset: str | None
    time_window_seconds: int | None

    @property
    def reset_datetime(self) -> dt.datetime | None:
        if not self.reset:
            return None
        try:
            return dt.datetime.fromisoformat(self.reset.replace("Z", "+00:00"))
        except ValueError:
            return None


def fetch_browse_quota() -> EbayBrowseQuota | None:
    token = get_app_access_token()
    response = requests.get(
        EBAY_RATE_LIMIT_URL,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    return parse_browse_quota(response.json())


def get_app_access_token() -> str:
    credentials = f"{required_env('EBAY_CLIENT_ID')}:{required_env('EBAY_CLIENT_SECRET')}"
    response = requests.post(
        EBAY_TOKEN_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {base64.b64encode(credentials.encode()).decode()}",
        },
        data={
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def parse_browse_quota(payload: dict[str, Any]) -> EbayBrowseQuota | None:
    for api in payload.get("rateLimits") or []:
        if str(api.get("apiName") or "").casefold() != "browse":
            continue
        for resource in api.get("resources") or []:
            if str(resource.get("name") or "").casefold() != EBAY_BROWSE_RESOURCE:
                continue
            rates = resource.get("rates") or []
            rate = rates[0] if rates else {}
            return EbayBrowseQuota(
                resource=EBAY_BROWSE_RESOURCE,
                limit=to_int(rate.get("limit")),
                count=to_int(rate.get("count")),
                remaining=to_int(rate.get("remaining")),
                reset=rate.get("reset"),
                time_window_seconds=to_int_or_none(rate.get("timeWindow")),
            )
    return None


def browse_call_budget(quota: EbayBrowseQuota | None, reserve: int | None = None) -> int | None:
    if quota is None:
        return None
    reserve_calls = reserve if reserve is not None else int(os.getenv("EBAY_BROWSE_QUOTA_RESERVE", "0") or 0)
    return max(quota.remaining - max(reserve_calls, 0), 0)


def quota_summary(quota: EbayBrowseQuota | None) -> dict[str, Any]:
    if quota is None:
        return {"resource": EBAY_BROWSE_RESOURCE, "available": False}
    return {
        "resource": quota.resource,
        "limit": quota.limit,
        "count": quota.count,
        "remaining": quota.remaining,
        "reset": quota.reset,
        "time_window_seconds": quota.time_window_seconds,
    }


def to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return to_int(value)
