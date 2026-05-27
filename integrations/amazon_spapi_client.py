"""Read-only Amazon SP-API client foundation for MBOP.

This module intentionally avoids restricted-data-token flows and PII-oriented
operations. It supports seller-authorized read calls with LWA access tokens.
Legacy AWS SigV4 signing remains available only when explicitly enabled,
preserving the MBOP pattern where Python integrations read external systems and
later write normalized data to Supabase.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode, urlparse

import requests
from dotenv import find_dotenv, load_dotenv

LOGGER = logging.getLogger("amazon_spapi")

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
SERVICE_NAME = "execute-api"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_RETRY_DELAY_SECONDS = 2.0

REGION_ENDPOINTS = {
    "na": ("https://sellingpartnerapi-na.amazon.com", "us-east-1"),
    "us-east-1": ("https://sellingpartnerapi-na.amazon.com", "us-east-1"),
    "eu": ("https://sellingpartnerapi-eu.amazon.com", "eu-west-1"),
    "eu-west-1": ("https://sellingpartnerapi-eu.amazon.com", "eu-west-1"),
    "fe": ("https://sellingpartnerapi-fe.amazon.com", "us-west-2"),
    "us-west-2": ("https://sellingpartnerapi-fe.amazon.com", "us-west-2"),
}

READ_ONLY_OPERATION_PREFIXES = (
    "/fba/inventory/",
    "/finances/v0/financialEventGroups",
    "/finances/v0/financialEventGroups/",
    "/finances/2024-06-19/transactions",
    "/listings/2021-08-01/items/",
    "/products/pricing/",
    "/reports/2021-06-30/",
)

ALLOWED_REPORT_TYPES = {
    "GET_FBA_INVENTORY_PLANNING_DATA",
}


class AmazonSPAPIError(RuntimeError):
    """Raised when Amazon SP-API auth or request handling fails safely."""


@dataclass(frozen=True)
class AmazonSPAPIConfig:
    client_id: str
    client_secret: str
    refresh_token: str
    marketplace_id: str
    endpoint: str
    aws_region: str
    app_id: str = "MBOP"
    seller_id: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    use_sigv4: bool = False

    @classmethod
    def from_env(cls) -> "AmazonSPAPIConfig":
        dotenv_path = find_dotenv(usecwd=True)
        load_dotenv(dotenv_path or None)
        log_refresh_token_diagnostics(dotenv_path)
        region_value = env("AMAZON_SP_API_REGION", "na").lower()
        endpoint, aws_region = REGION_ENDPOINTS.get(
            region_value, REGION_ENDPOINTS["na"]
        )

        return cls(
            client_id=required_env("AMAZON_SP_API_CLIENT_ID"),
            client_secret=required_env("AMAZON_SP_API_CLIENT_SECRET"),
            refresh_token=required_env("AMAZON_SP_API_REFRESH_TOKEN"),
            marketplace_id=required_env("AMAZON_SP_API_MARKETPLACE_ID"),
            endpoint=env("AMAZON_SP_API_ENDPOINT", endpoint).rstrip("/"),
            aws_region=env("AMAZON_SP_API_AWS_REGION", aws_region),
            app_id=env("AMAZON_SP_API_APP_ID", "MBOP"),
            seller_id=(
                env("AMAZON_SP_API_SELLER_ID")
                or env("AMAZON_SELLER_ID")
                or env("AMAZON_MERCHANT_ID")
                or None
            ),
            aws_access_key_id=env(
                "AMAZON_SP_API_AWS_ACCESS_KEY_ID",
                env("AWS_ACCESS_KEY_ID"),
            )
            or None,
            aws_secret_access_key=env(
                "AMAZON_SP_API_AWS_SECRET_ACCESS_KEY",
                env("AWS_SECRET_ACCESS_KEY"),
            )
            or None,
            aws_session_token=env(
                "AMAZON_SP_API_AWS_SESSION_TOKEN",
                env("AWS_SESSION_TOKEN"),
            )
            or None,
            use_sigv4=env("AMAZON_SP_API_USE_SIGV4").lower()
            in {"1", "true", "yes"},
        )

    def missing_sigv4_fields(self) -> list[str]:
        missing = []
        if not self.aws_access_key_id:
            missing.append("AMAZON_SP_API_AWS_ACCESS_KEY_ID or AWS_ACCESS_KEY_ID")
        if not self.aws_secret_access_key:
            missing.append(
                "AMAZON_SP_API_AWS_SECRET_ACCESS_KEY or AWS_SECRET_ACCESS_KEY"
            )
        return missing


class AmazonSPAPIClient:
    def __init__(
        self,
        config: AmazonSPAPIConfig | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.config = config or AmazonSPAPIConfig.from_env()
        self.session = session or requests.Session()
        self._access_token: str | None = None
        self._access_token_expires_at: dt.datetime | None = None

    @classmethod
    def from_env(cls) -> "AmazonSPAPIClient":
        return cls(AmazonSPAPIConfig.from_env())

    def test_lwa_access_token(self) -> dict[str, Any]:
        token = self.get_lwa_access_token(force_refresh=True)
        return {
            "token_received": bool(token),
            "expires_at": self._access_token_expires_at.isoformat()
            if self._access_token_expires_at
            else None,
        }

    def get_lwa_access_token(self, force_refresh: bool = False) -> str:
        now = utc_now()
        if (
            not force_refresh
            and self._access_token
            and self._access_token_expires_at
            and self._access_token_expires_at > now + dt.timedelta(minutes=5)
        ):
            return self._access_token

        LOGGER.info("Requesting Amazon LWA access token")
        response = self.session.post(
            LWA_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.config.refresh_token,
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "User-Agent": self.user_agent(),
            },
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )

        if not response.ok:
            raise AmazonSPAPIError(
                f"LWA token request failed with HTTP {response.status_code}: "
                f"{safe_response_text(response)}"
            )

        payload = response.json()
        access_token = payload.get("access_token")
        expires_in = int(payload.get("expires_in") or 0)
        if not access_token or expires_in <= 0:
            raise AmazonSPAPIError("LWA token response did not include a usable token")

        self._access_token = access_token
        self._access_token_expires_at = now + dt.timedelta(seconds=expires_in)
        LOGGER.info("Amazon LWA access token received; expires_in=%s", expires_in)
        return access_token

    def get_inventory_summaries(
        self,
        *,
        details: bool = True,
        seller_skus: list[str] | None = None,
        next_token: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "details": str(details).lower(),
            "granularityType": "Marketplace",
            "granularityId": self.config.marketplace_id,
            "marketplaceIds": self.config.marketplace_id,
        }
        if seller_skus:
            params["sellerSkus"] = seller_skus[:50]
        if next_token:
            params["nextToken"] = next_token

        return self.request("GET", "/fba/inventory/v1/summaries", params=params)

    def iter_inventory_summaries(
        self,
        *,
        details: bool = True,
        seller_skus: list[str] | None = None,
        max_pages: int | None = None,
        page_delay_seconds: float = 0.0,
    ):
        next_token: str | None = None
        pages_seen = 0

        while True:
            payload = self.get_inventory_summaries(
                details=details,
                seller_skus=seller_skus,
                next_token=next_token,
            )
            pages_seen += 1
            inventory_payload = payload.get("payload") or {}
            for summary in inventory_payload.get("inventorySummaries") or []:
                yield summary

            next_token = (
                (payload.get("pagination") or {}).get("nextToken")
                or inventory_payload.get("nextToken")
            )
            if not next_token:
                return
            if max_pages and pages_seen >= max_pages:
                LOGGER.warning(
                    "Stopping Amazon inventory pagination at max_pages=%s",
                    max_pages,
                )
                return
            if page_delay_seconds > 0:
                time.sleep(page_delay_seconds)

    def get_listing_item(
        self,
        seller_sku: str,
        *,
        included_data: list[str] | None = None,
        seller_id: str | None = None,
    ) -> dict[str, Any]:
        selling_partner_id = seller_id or self.config.seller_id
        if not selling_partner_id:
            raise AmazonSPAPIError(
                "AMAZON_SP_API_SELLER_ID is required for getListingsItem"
            )

        params: dict[str, Any] = {
            "marketplaceIds": self.config.marketplace_id,
        }
        if included_data:
            params["includedData"] = ",".join(included_data)

        path = (
            "/listings/2021-08-01/items/"
            f"{quote(selling_partner_id, safe='')}/{quote(seller_sku, safe='')}"
        )
        return self.request("GET", path, params=params)

    def get_item_offers(
        self,
        asin: str,
        *,
        item_condition: str = "New",
    ) -> dict[str, Any]:
        params = {
            "MarketplaceId": self.config.marketplace_id,
            "ItemCondition": item_condition,
        }
        path = f"/products/pricing/v0/items/{quote(asin, safe='')}/offers"
        return self.request("GET", path, params=params)

    def get_listing_offers(
        self,
        seller_sku: str,
        *,
        item_condition: str = "New",
    ) -> dict[str, Any]:
        params = {
            "MarketplaceId": self.config.marketplace_id,
            "ItemCondition": item_condition,
        }
        path = f"/products/pricing/v0/listings/{quote(seller_sku, safe='')}/offers"
        return self.request("GET", path, params=params)

    def create_report(
        self,
        report_type: str,
        *,
        marketplace_ids: list[str] | None = None,
        report_options: dict[str, Any] | None = None,
        data_start_time: str | None = None,
        data_end_time: str | None = None,
    ) -> dict[str, Any]:
        if report_type not in ALLOWED_REPORT_TYPES:
            raise AmazonSPAPIError(
                f"Amazon report type is outside the MBOP allow-list: {report_type}"
            )

        body: dict[str, Any] = {
            "reportType": report_type,
            "marketplaceIds": marketplace_ids or [self.config.marketplace_id],
        }
        if report_options:
            body["reportOptions"] = report_options
        if data_start_time:
            body["dataStartTime"] = data_start_time
        if data_end_time:
            body["dataEndTime"] = data_end_time

        return self.request("POST", "/reports/2021-06-30/reports", json_body=body)

    def get_report(self, report_id: str) -> dict[str, Any]:
        path = f"/reports/2021-06-30/reports/{quote(report_id, safe='')}"
        return self.request("GET", path)

    def get_report_document(self, report_document_id: str) -> dict[str, Any]:
        path = f"/reports/2021-06-30/documents/{quote(report_document_id, safe='')}"
        return self.request("GET", path)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        method = method.upper()
        self.validate_read_only_request(method, path)

        body = json.dumps(json_body, separators=(",", ":")) if json_body else ""
        url = f"{self.config.endpoint}{path}"
        access_token = self.get_lwa_access_token()
        headers = {
            "user-agent": self.user_agent(),
            "x-amz-access-token": access_token,
        }
        if body:
            headers["content-type"] = "application/json"

        request_headers = headers
        if self.config.use_sigv4:
            missing_sigv4 = self.config.missing_sigv4_fields()
            if missing_sigv4:
                raise AmazonSPAPIError(
                    "AMAZON_SP_API_USE_SIGV4 is enabled, but signing credentials "
                    f"are missing: {', '.join(missing_sigv4)}"
                )

            request_time = utc_now()
            signing_headers = {
                **headers,
                "host": urlparse(self.config.endpoint).netloc,
                "x-amz-date": request_time.strftime("%Y%m%dT%H%M%SZ"),
            }
            if self.config.aws_session_token:
                signing_headers["x-amz-security-token"] = (
                    self.config.aws_session_token
                )
            request_headers = self.sign_v4(
                method=method,
                url=url,
                params=params or {},
                headers=signing_headers,
                body=body,
                request_time=request_time,
            )

        response = None
        for attempt in range(1, DEFAULT_MAX_ATTEMPTS + 1):
            LOGGER.info("Amazon SP-API %s %s", method, path)
            response = self.session.request(
                method,
                url,
                params=params,
                data=body or None,
                headers=request_headers,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )

            if response.ok:
                break

            if response.status_code not in {429, 500, 502, 503, 504}:
                break

            if attempt >= DEFAULT_MAX_ATTEMPTS:
                break

            retry_delay = retry_delay_seconds(response, attempt)
            LOGGER.warning(
                "Amazon SP-API %s %s returned HTTP %s; retrying in %.1fs "
                "(attempt %s/%s)",
                method,
                path,
                response.status_code,
                retry_delay,
                attempt,
                DEFAULT_MAX_ATTEMPTS,
            )
            time.sleep(retry_delay)

        if response is None:
            raise AmazonSPAPIError(f"Amazon SP-API {method} {path} was not attempted")

        if not response.ok:
            raise AmazonSPAPIError(
                f"Amazon SP-API {method} {path} failed with HTTP "
                f"{response.status_code}: {safe_response_text(response)}"
            )

        if not response.text.strip():
            return {}

        return response.json()

    def validate_read_only_request(self, method: str, path: str) -> None:
        if method != "GET":
            if not (method == "POST" and path == "/reports/2021-06-30/reports"):
                raise AmazonSPAPIError("MBOP Amazon SP-API foundation is read-only")

        if not path.startswith(READ_ONLY_OPERATION_PREFIXES):
            raise AmazonSPAPIError(
                f"Amazon SP-API path is outside the read-only MBOP allow-list: {path}"
            )

    def sign_v4(
        self,
        *,
        method: str,
        url: str,
        params: dict[str, Any],
        headers: dict[str, str],
        body: str,
        request_time: dt.datetime,
    ) -> dict[str, str]:
        parsed_url = urlparse(url)
        amz_date = request_time.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = request_time.strftime("%Y%m%d")
        canonical_uri = parsed_url.path or "/"
        canonical_querystring = canonical_query(params)
        canonical_headers, signed_header_names = canonicalize_headers(headers)
        payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        canonical_request = "\n".join(
            [
                method,
                canonical_uri,
                canonical_querystring,
                canonical_headers,
                signed_header_names,
                payload_hash,
            ]
        )
        credential_scope = (
            f"{date_stamp}/{self.config.aws_region}/{SERVICE_NAME}/aws4_request"
        )
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = get_signature_key(
            self.config.aws_secret_access_key or "",
            date_stamp,
            self.config.aws_region,
            SERVICE_NAME,
        )
        signature = hmac.new(
            signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        authorization_header = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self.config.aws_access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_header_names}, "
            f"Signature={signature}"
        )

        return {
            **headers,
            "Authorization": authorization_header,
        }

    def user_agent(self) -> str:
        safe_app_id = (self.config.app_id or "MBOP").replace("/", "-")
        return f"{safe_app_id}/0.1 (Language=Python)"


def canonical_query(params: dict[str, Any]) -> str:
    pairs: list[tuple[str, str]] = []
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            values = value
        else:
            values = [value]
        for item in values:
            pairs.append((str(key), str(item)))

    return urlencode(sorted(pairs), doseq=True, quote_via=quote, safe="-_.~")


def canonicalize_headers(headers: dict[str, str]) -> tuple[str, str]:
    normalized = {
        key.lower().strip(): " ".join(str(value).strip().split())
        for key, value in headers.items()
    }
    signed_names = sorted(normalized.keys())
    canonical_headers = "".join(
        f"{name}:{normalized[name]}\n" for name in signed_names
    )
    return canonical_headers, ";".join(signed_names)


def get_signature_key(
    key: str,
    date_stamp: str,
    region_name: str,
    service_name: str,
) -> bytes:
    k_date = sign(("AWS4" + key).encode("utf-8"), date_stamp)
    k_region = sign(k_date, region_name)
    k_service = sign(k_region, service_name)
    return sign(k_service, "aws4_request")


def sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def env(name: str, default: str | None = None) -> str:
    return os.getenv(name, default or "").strip()


def required_env(name: str) -> str:
    value = env(name)
    if not value:
        raise AmazonSPAPIError(f"Missing required environment variable: {name}")
    return value


def log_refresh_token_diagnostics(dotenv_path: str | None) -> None:
    token = env("AMAZON_SP_API_REFRESH_TOKEN")
    if not token:
        LOGGER.info(
            "Amazon refresh token diagnostics: .env=%s token=missing",
            dotenv_path or "<not found>",
        )
        return

    LOGGER.info(
        "Amazon refresh token diagnostics: .env=%s length=%s prefix=%s suffix=%s",
        dotenv_path or "<not found>",
        len(token),
        token[:6],
        token[-6:],
    )


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def safe_response_text(response: requests.Response) -> str:
    text = response.text.strip()
    if not text:
        return "<empty response>"
    return text[:1000]


def retry_delay_seconds(response: requests.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(1.0, float(retry_after))
        except ValueError:
            LOGGER.debug("Ignoring non-numeric Retry-After header: %s", retry_after)

    return DEFAULT_RETRY_DELAY_SECONDS * attempt
