"""Read-only Informed Repricer Reports API client for MBOP.

This client is intentionally scoped to report request/status/download behavior.
It does not call the Listings Management API, upload feeds, or modify prices,
rules, min/max prices, or Informed settings.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import requests
from dotenv import load_dotenv

LOGGER = logging.getLogger("informed_repricing_client")
DEFAULT_ENDPOINT = "https://api.informedrepricer.com"
DEFAULT_TIMEOUT_SECONDS = 60


class InformedAPIError(RuntimeError):
    """Raised when Informed auth or request handling fails safely."""


@dataclass(frozen=True)
class InformedConfig:
    api_key: str
    endpoint: str = DEFAULT_ENDPOINT

    @classmethod
    def from_env(cls) -> "InformedConfig":
        load_dotenv()
        return cls(
            api_key=required_env("INFORMED_REPRICER_API_KEY"),
            endpoint=env("INFORMED_REPRICER_ENDPOINT", DEFAULT_ENDPOINT).rstrip("/"),
        )


class InformedRepricingClient:
    def __init__(
        self,
        config: InformedConfig | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.config = config or InformedConfig.from_env()
        self.session = session or requests.Session()

    @classmethod
    def from_env(cls) -> "InformedRepricingClient":
        return cls(InformedConfig.from_env())

    def list_report_requests(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        return self.request("GET", "/reports/requests", params=params)

    def request_report(self, report_type: str) -> dict[str, Any]:
        if not report_type:
            raise InformedAPIError("report_type is required")
        return self.request(
            "GET",
            "/reports/requestReport",
            params={"reportType": report_type},
        )

    def get_report_request_status(self, report_request_id: str) -> dict[str, Any]:
        if not report_request_id:
            raise InformedAPIError("report_request_id is required")
        return self.request("GET", f"/reports/requests/{report_request_id}")

    def download_report(self, download_url: str) -> bytes:
        if not download_url.startswith(("http://", "https://")):
            raise InformedAPIError("Informed report download URL is not HTTP(S)")
        LOGGER.info("Downloading Informed report from signed URL")
        response = self.session.get(download_url, timeout=DEFAULT_TIMEOUT_SECONDS)
        if not response.ok:
            raise InformedAPIError(
                f"Informed report download failed with HTTP {response.status_code}: "
                f"{safe_response_text(response)}"
            )
        return response.content

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        method = method.upper()
        if method != "GET":
            raise InformedAPIError("MBOP Informed integration is read-only")
        if not path.startswith("/reports/"):
            raise InformedAPIError(
                f"Informed path is outside the read-only Reports API scope: {path}"
            )

        url = f"{self.config.endpoint}{path}"
        safe_params = dict(params or {})
        LOGGER.info("Informed GET %s params=%s", path, safe_params)
        response = self.session.get(
            url,
            params=params,
            headers={
                "x-api-key": self.config.api_key,
                "accept": "application/json",
                "user-agent": "MBOP/0.1 (Language=Python)",
            },
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )

        if not response.ok:
            raise InformedAPIError(
                f"Informed GET {path} failed with HTTP {response.status_code}: "
                f"{safe_response_text(response)}"
            )
        if not response.text.strip():
            return {}
        try:
            return response.json()
        except ValueError as error:
            raise InformedAPIError("Informed response was not valid JSON") from error


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def required_env(name: str) -> str:
    value = env(name)
    if not value:
        raise InformedAPIError(f"Missing required environment variable: {name}")
    return value


def safe_response_text(response: requests.Response, max_length: int = 1000) -> str:
    text = response.text or ""
    if len(text) > max_length:
        return f"{text[:max_length]}..."
    return text
