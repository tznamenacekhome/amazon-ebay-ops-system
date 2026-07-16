"""Read-only Keepa API client for MBOP catalog intelligence.

Keepa is used for product-level research such as price history, sales-rank
history, sales-rank drops, Buy Box context, and offer signals. This client does
not write to MBOP data stores; sync scripts decide where normalized snapshots
belong.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import requests
from dotenv import load_dotenv

LOGGER = logging.getLogger("keepa_client")
DEFAULT_ENDPOINT = "https://api.keepa.com"
DEFAULT_TIMEOUT_SECONDS = 45
TRANSIENT_REQUEST_ATTEMPTS = 3


class KeepaAPIError(RuntimeError):
    """Raised when Keepa auth or request handling fails safely."""


@dataclass(frozen=True)
class KeepaConfig:
    api_key: str
    endpoint: str = DEFAULT_ENDPOINT
    domain_id: int = 1

    @classmethod
    def from_env(cls) -> "KeepaConfig":
        load_dotenv()
        return cls(
            api_key=required_env("KEEPA_API_KEY"),
            endpoint=env("KEEPA_API_ENDPOINT", DEFAULT_ENDPOINT).rstrip("/"),
            domain_id=int(env("KEEPA_DOMAIN_ID", "1")),
        )


class KeepaClient:
    def __init__(
        self,
        config: KeepaConfig | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.config = config or KeepaConfig.from_env()
        self.session = session or requests.Session()

    @classmethod
    def from_env(cls) -> "KeepaClient":
        return cls(KeepaConfig.from_env())

    def get_token_status(self) -> dict[str, Any]:
        payload = self.request("token", params={})
        return {
            "tokens_left": payload.get("tokensLeft"),
            "refill_in": payload.get("refillIn"),
            "refill_rate": payload.get("refillRate"),
            "raw": payload,
        }

    def get_products(
        self,
        asins: list[str],
        *,
        stats_days: int = 90,
        history: bool = True,
        offers: int | None = None,
        stock: bool = False,
        rating: bool = True,
        wait: bool = True,
    ) -> dict[str, Any]:
        clean_asins = [asin.strip().upper() for asin in asins if asin and asin.strip()]
        if not clean_asins:
            return {"products": []}
        if len(clean_asins) > 100:
            raise KeepaAPIError("Keepa product calls support at most 100 ASINs per request.")

        params: dict[str, Any] = {
            "domain": self.config.domain_id,
            "asin": ",".join(clean_asins),
            "stats": stats_days,
            "history": 1 if history else 0,
            "rating": 1 if rating else 0,
            "wait": 1 if wait else 0,
        }
        if offers is not None:
            params["offers"] = offers
        if stock:
            params["stock"] = 1

        return self.request("product", params=params)

    def request(self, path: str, *, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.config.endpoint}/{path.lstrip('/')}"
        request_params = {"key": self.config.api_key, **params}
        safe_params = {key: value for key, value in request_params.items() if key != "key"}
        LOGGER.info("Keepa GET /%s params=%s", path.lstrip("/"), safe_params)

        response = None
        for attempt in range(1, TRANSIENT_REQUEST_ATTEMPTS + 1):
            try:
                response = self.session.get(
                    url,
                    params=request_params,
                    timeout=DEFAULT_TIMEOUT_SECONDS,
                )
                break
            except (requests.Timeout, requests.ConnectionError) as error:
                if attempt >= TRANSIENT_REQUEST_ATTEMPTS:
                    raise KeepaAPIError(f"Keepa request failed after retries: {error}") from error
                sleep_seconds = min(2 ** attempt, 10)
                LOGGER.warning(
                    "Keepa GET /%s transient failure on attempt %s/%s: %s; retrying in %ss",
                    path.lstrip("/"),
                    attempt,
                    TRANSIENT_REQUEST_ATTEMPTS,
                    error,
                    sleep_seconds,
                )
                time.sleep(sleep_seconds)

        if response is None:
            raise KeepaAPIError("Keepa request did not return a response.")

        if response.status_code == 429:
            raise KeepaAPIError("Keepa token/rate limit reached: HTTP 429")
        if not response.ok:
            raise KeepaAPIError(
                f"Keepa request failed with HTTP {response.status_code}: "
                f"{safe_response_text(response)}"
            )

        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise KeepaAPIError(f"Keepa returned error: {payload.get('error')}")
        return payload

    def wait_for_refill(self, token_status: dict[str, Any], *, min_tokens: int) -> None:
        tokens_left = to_int(token_status.get("tokens_left"), default=0)
        if tokens_left >= min_tokens:
            return
        refill_ms = to_int(token_status.get("refill_in"), default=0)
        sleep_seconds = max(refill_ms / 1000, 1)
        LOGGER.warning(
            "Keepa tokens_left=%s below min_tokens=%s; sleeping %.1fs for refill",
            tokens_left,
            min_tokens,
            sleep_seconds,
        )
        time.sleep(sleep_seconds)


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def required_env(name: str) -> str:
    value = env(name)
    if not value:
        raise KeepaAPIError(f"Missing required environment variable: {name}")
    return value


def to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_response_text(response: requests.Response, max_length: int = 500) -> str:
    text = response.text or ""
    if len(text) > max_length:
        return f"{text[:max_length]}..."
    return text
