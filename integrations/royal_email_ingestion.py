"""Poll the scoped Royal mailbox sources and import validated price lists."""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import logging
import os
import re
import socket
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from sourcing_common import get_supabase_client
from wholesale_repository import WholesaleRepository
from wholesale_royal import parse_price_list

LOGGER = logging.getLogger("royal_email_ingestion")
MAILBOX = "tim@midnightbe.com"
SENDERS = ("sales@royalelec.com", "gp@royalelec.com")
MARKETPLACE_ID = "ATVPDKIKX0DER"
MAX_BYTES = 10 * 1024 * 1024
SUPPORTED = {".xlsx", ".xls", ".csv"}


class IntakeError(Exception):
    def __init__(self, code: str, message: str, *, transient: bool = False):
        super().__init__(message)
        self.code, self.transient = code, transient


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(html.unescape(href))


class GraphClient:
    def __init__(self, tenant_id: str, client_id: str, client_secret: str,
                 session: requests.Session | None = None) -> None:
        self.tenant_id, self.client_id, self.client_secret = tenant_id, client_id, client_secret
        self.session = session or requests.Session()
        self._token: str | None = None

    def token(self) -> str:
        if self._token:
            return self._token
        response = self.session.post(
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token",
            data={"client_id": self.client_id, "client_secret": self.client_secret,
                  "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"},
            timeout=30,
        )
        if response.status_code >= 400:
            raise IntakeError("graph_auth_failed", "Microsoft Graph authentication failed", transient=response.status_code >= 500)
        self._token = response.json().get("access_token")
        if not self._token:
            raise IntakeError("graph_auth_failed", "Microsoft Graph returned no access token")
        return self._token

    def get(self, path: str, params: dict | None = None, *, raw: bool = False):
        response = self.session.get(f"https://graph.microsoft.com/v1.0{path}", params=params,
                                    headers={"Authorization": f"Bearer {self.token()}"}, timeout=45)
        if response.status_code >= 400:
            raise IntakeError("graph_read_failed", f"Microsoft Graph read failed ({response.status_code})",
                              transient=response.status_code in {429, 500, 502, 503, 504})
        return response.content if raw else response.json()

    def messages(self, mailbox: str, since: dt.datetime, max_pages: int = 4) -> list[dict]:
        output: dict[str, dict] = {}
        for sender in SENDERS:
            path = f"/users/{mailbox}/mailFolders/inbox/messages"
            params = {"$select": "id,internetMessageId,subject,receivedDateTime,from,hasAttachments,body",
                      "$filter": f"receivedDateTime ge {since.isoformat().replace('+00:00','Z')} and from/emailAddress/address eq '{sender}'",
                      "$orderby": "receivedDateTime asc", "$top": "50"}
            for _ in range(max_pages):
                payload = self.get(path, params)
                for message in payload.get("value", []):
                    output[message["id"]] = message
                next_link = payload.get("@odata.nextLink")
                if not next_link:
                    break
                parsed = urlparse(next_link)
                path, params = parsed.path.removeprefix("/v1.0"), dict(
                    (key, values[-1]) for key, values in parse_qs(parsed.query).items())
        return sorted(output.values(), key=lambda row: row.get("receivedDateTime", ""))

    def message(self, mailbox: str, message_id: str) -> dict:
        return self.get(
            f"/users/{mailbox}/messages/{message_id}",
            {"$select": "id,internetMessageId,subject,receivedDateTime,from,hasAttachments,body"},
        )

    def attachments(self, mailbox: str, message_id: str) -> list[dict]:
        payload = self.get(f"/users/{mailbox}/messages/{message_id}/attachments",
                           {"$select": "id,name,contentType,size,isInline"})
        return payload.get("value", [])

    def attachment_bytes(self, mailbox: str, message_id: str, attachment: dict) -> bytes:
        encoded = attachment.get("contentBytes")
        if encoded:
            return base64.b64decode(encoded, validate=True)
        return self.get(f"/users/{mailbox}/messages/{message_id}/attachments/{attachment['id']}/$value", raw=True)


def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._ -]", "_", Path(name).name)[:180]


def validate_source(name: str, content: bytes) -> None:
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED:
        raise IntakeError("unsupported_format", "Royal source is not XLSX, XLS, or CSV")
    if not content or len(content) > MAX_BYTES:
        raise IntakeError("invalid_size", "Royal source is empty or exceeds 10 MiB")
    if suffix == ".xlsx" and not content.startswith(b"PK"):
        raise IntakeError("invalid_file_signature", "XLSX file signature is invalid")
    if suffix == ".xls" and not content.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        raise IntakeError("invalid_file_signature", "XLS file signature is invalid")
    if suffix == ".csv" and b"\x00" in content[:8192]:
        raise IntakeError("invalid_file_signature", "CSV contains binary data")


def body_links(body: dict) -> list[str]:
    content = str((body or {}).get("content") or "")
    collector = LinkCollector()
    collector.feed(content)
    links = collector.links + re.findall(r"https://[^\s<>\"']+", content)
    return list(dict.fromkeys(link.rstrip(".,);\"") for link in links))


def allowed_host(host: str, allowed: set[str]) -> bool:
    host = host.lower().rstrip(".")
    return any(host == candidate or host.endswith("." + candidate) for candidate in allowed)


def download_link(url: str, allowed: set[str], session: requests.Session | None = None) -> tuple[str, bytes, str]:
    session = session or requests.Session()
    current = url
    for _ in range(4):
        parsed = urlparse(current)
        if parsed.scheme != "https" or not parsed.hostname or not allowed_host(parsed.hostname, allowed):
            raise IntakeError("link_host_blocked", "Secure link host is not approved")
        response = session.get(current, allow_redirects=False, timeout=45, stream=True)
        if response.status_code in {301, 302, 303, 307, 308}:
            current = requests.compat.urljoin(current, response.headers.get("Location", ""))
            continue
        if response.status_code >= 400:
            raise IntakeError("download_failed", f"Secure download failed ({response.status_code})",
                              transient=response.status_code in {429, 500, 502, 503, 504})
        length = int(response.headers.get("Content-Length") or 0)
        if length > MAX_BYTES:
            raise IntakeError("invalid_size", "Royal source exceeds 10 MiB")
        content = bytearray()
        for chunk in response.iter_content(65536):
            content.extend(chunk)
            if len(content) > MAX_BYTES:
                raise IntakeError("invalid_size", "Royal source exceeds 10 MiB")
        disposition = response.headers.get("Content-Disposition", "")
        match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disposition, re.I)
        name = safe_filename(requests.utils.unquote(match.group(1)) if match else Path(parsed.path).name)
        if Path(name).suffix.lower() not in SUPPORTED:
            content_type = response.headers.get("Content-Type", "").lower()
            extension = ".xlsx" if "spreadsheetml" in content_type else ".xls" if "ms-excel" in content_type else ".csv" if "csv" in content_type else ""
            name = (name or "royal-price-list") + extension
        validate_source(name, bytes(content))
        return name, bytes(content), parsed.hostname.lower()
    raise IntakeError("redirect_limit", "Secure download exceeded redirect limit")


class IntakeRepository:
    def __init__(self, client) -> None:
        self.client = client
        self.wholesale = WholesaleRepository(client)

    def checkpoint(self, message: dict, sender: str) -> dict:
        mailbox = MAILBOX.lower()
        existing = (self.client.table("wholesale_email_ingestions").select("*")
                    .eq("mailbox", mailbox).eq("graph_message_id", message["id"]).limit(1).execute().data or [])
        if existing:
            return existing[0]
        rows = self.client.table("wholesale_email_ingestions").insert({
            "mailbox": mailbox, "graph_message_id": message["id"],
            "internet_message_id": str(message.get("internetMessageId") or "")[:500] or None,
            "sender_address": sender, "subject": str(message.get("subject") or "")[:500],
            "received_at": message["receivedDateTime"], "status": "discovered",
        }).execute().data or []
        return rows[0]

    def update(self, ingestion_id: str, values: dict) -> None:
        values["updated_at"] = now_iso()
        self.client.table("wholesale_email_ingestions").update(values).eq("ingestion_id", ingestion_id).execute()

    def notify(self, key: str, title: str, message: str, severity: str = "error") -> None:
        self.wholesale.operational_notification(key, title, message, severity)

    def alert_if_stale(self, hours: int) -> None:
        rows = (self.client.table("wholesale_email_ingestions").select("received_at")
                .order("received_at", desc=True).limit(1).execute().data or [])
        if not rows:
            return
        latest = dt.datetime.fromisoformat(rows[0]["received_at"].replace("Z", "+00:00"))
        if latest < dt.datetime.now(dt.UTC) - dt.timedelta(hours=hours):
            self.notify("royal-email:silence", "Royal price list email is overdue",
                        f"No approved Royal message has been observed for more than {hours} hours.", "warning")

    def supplier(self) -> dict:
        rows = (self.client.table("wholesale_suppliers").select("supplier_id")
                .eq("supplier_key", "royal-electronics").limit(1).execute().data or [])
        if not rows:
            raise IntakeError("supplier_missing", "Royal supplier record is missing")
        return rows[0]

    def replay_checkpoints(self, effective_dates: list[str]) -> list[dict]:
        if not effective_dates:
            return []
        return (self.client.table("wholesale_email_ingestions")
                .select("graph_message_id,effective_date,received_at,status")
                .eq("mailbox", MAILBOX).in_("effective_date", effective_dates)
                .in_("status", ["completed", "duplicate"])
                .order("received_at", desc=True).execute().data or [])

    def queue_downstream(self, supplier_id: str, import_id: str) -> str | None:
        observations = (self.client.table("wholesale_supplier_observations")
                        .select("observation_id,supplier_product_id").eq("import_id", import_id).execute().data or [])
        product_ids = [row["supplier_product_id"] for row in observations]
        states = []
        for start in range(0, len(product_ids), 150):
            states.extend((self.client.table("wholesale_match_states").select("supplier_product_id,match_status,rematch_requested,updated_at,selected_candidate_id")
                           .eq("marketplace_id", MARKETPLACE_ID).in_("supplier_product_id", product_ids[start:start + 150]).execute().data or []))
        by_product = {row["supplier_product_id"]: row for row in states}
        already_queued = self.wholesale.active_work_product_ids(product_ids)
        stale_before = dt.datetime.now(dt.UTC) - dt.timedelta(days=30)
        match_ids = []
        for observation in observations:
            state = by_product.get(observation["supplier_product_id"])
            stale = bool(state and dt.datetime.fromisoformat(state["updated_at"].replace("Z", "+00:00")) < stale_before)
            if (not state or state.get("rematch_requested") or stale or
                    state.get("match_status") in {"discovery_pending", "no_candidates"}):
                if observation["supplier_product_id"] in already_queued:
                    continue
                match_ids.append(observation["supplier_product_id"])
            else:
                self.wholesale.ensure_opportunity(observation["supplier_product_id"], MARKETPLACE_ID,
                                                  state["selected_candidate_id"], observation["observation_id"])
        run = self.wholesale.create_targeted_enrichment_run(supplier_id, MARKETPLACE_ID, match_ids)
        return run["enrichment_run_id"] if run else None


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def select_source(graph: GraphClient, message: dict, allowed_domains: set[str]) -> tuple[str, str, bytes, str | None]:
    if message.get("hasAttachments"):
        for attachment in graph.attachments(MAILBOX, message["id"]):
            name = safe_filename(str(attachment.get("name") or ""))
            if attachment.get("isInline") or Path(name).suffix.lower() not in SUPPORTED:
                continue
            if int(attachment.get("size") or 0) > MAX_BYTES:
                raise IntakeError("invalid_size", "Royal attachment exceeds 10 MiB")
            content = graph.attachment_bytes(MAILBOX, message["id"], attachment)
            validate_source(name, content)
            return "attachment", name, content, None
    for link in body_links(message.get("body") or {}):
        parsed = urlparse(link)
        if parsed.hostname and allowed_host(parsed.hostname, allowed_domains):
            name, content, host = download_link(link, allowed_domains)
            return "secure_link", name, content, host
    raise IntakeError("source_missing", "No supported Royal attachment or approved secure link was found")


def process_message(graph: GraphClient, repository: IntakeRepository, message: dict,
                    allowed_domains: set[str]) -> str:
    sender = str((((message.get("from") or {}).get("emailAddress") or {}).get("address")) or "").lower()
    if sender not in SENDERS:
        return "ignored"
    checkpoint = repository.checkpoint(message, sender)
    if checkpoint["status"] in {"completed", "duplicate", "rejected", "failed"}:
        return checkpoint["status"]
    if checkpoint.get("next_retry_at") and dt.datetime.fromisoformat(checkpoint["next_retry_at"].replace("Z", "+00:00")) > dt.datetime.now(dt.UTC):
        return "deferred"
    ingestion_id = checkpoint["ingestion_id"]
    attempt = int(checkpoint.get("attempt_count") or 0) + 1
    repository.update(ingestion_id, {"status": "processing", "attempt_count": attempt, "last_attempt_at": now_iso(),
                                     "next_retry_at": None, "error_code": None, "error_summary": None})
    try:
        source_type, name, content, host = select_source(graph, message, allowed_domains)
        with tempfile.TemporaryDirectory(prefix="mbop-royal-") as directory:
            path = Path(directory) / name
            path.write_bytes(content)
            try:
                payload = parse_price_list(path, filename_reference_date=message.get("receivedDateTime"))
            except ValueError as error:
                raise IntakeError("validation_failed", str(error)) from error
        if payload["status"] != "completed":
            reason = payload["errors"][0].get("reason", "Royal row validation failed") if payload["errors"] else "Royal row validation failed"
            raise IntakeError("validation_failed", reason)
        latest = repository.wholesale.latest_import_for_date(payload["supplier_key"], payload["effective_date"])
        replaces = latest["import_id"] if latest and latest["file_sha256"] != payload["file_sha256"] else None
        result = repository.wholesale.apply_import(payload, replaces)
        supplier_id = repository.supplier()["supplier_id"]
        run_id = repository.queue_downstream(supplier_id, result["import_id"])
        final_status = "duplicate" if result.get("already_imported") else "completed"
        repository.update(ingestion_id, {"supplier_id": supplier_id, "status": final_status,
            "source_type": source_type, "source_name": name, "source_host": host,
            "file_sha256": payload["file_sha256"], "effective_date": payload["effective_date"],
            "wholesale_import_id": result["import_id"], "enrichment_run_id": run_id, "completed_at": now_iso()})
        return final_status
    except IntakeError as error:
        permanent = not error.transient or attempt >= 5
        status = "failed" if permanent else "retry"
        retry_at = None if permanent else (dt.datetime.now(dt.UTC) + dt.timedelta(minutes=15 * (4 ** (attempt - 1)))).isoformat()
        repository.update(ingestion_id, {"status": status, "next_retry_at": retry_at,
                                         "error_code": error.code, "error_summary": str(error)[:1000]})
        if permanent:
            repository.notify(f"royal-email:{ingestion_id}:{error.code}", "Royal price list needs attention",
                              f"{str(error)} Sender: {sender}; received: {message.get('receivedDateTime')}.")
        return status
    except (requests.RequestException, socket.timeout) as error:
        retry_at = (dt.datetime.now(dt.UTC) + dt.timedelta(minutes=15 * (4 ** min(attempt - 1, 2)))).isoformat()
        repository.update(ingestion_id, {"status": "retry", "next_retry_at": retry_at,
                                         "error_code": "network_error", "error_summary": type(error).__name__})
        return "retry"
    except Exception as error:
        LOGGER.exception("Royal ingestion failed")
        permanent = attempt >= 5
        repository.update(ingestion_id, {"status": "failed" if permanent else "retry",
            "next_retry_at": None if permanent else (dt.datetime.now(dt.UTC) + dt.timedelta(minutes=15 * (4 ** min(attempt - 1, 2)))).isoformat(),
            "error_code": "unexpected_error", "error_summary": type(error).__name__})
        if permanent:
            repository.notify(f"royal-email:{ingestion_id}:unexpected", "Royal price list ingestion failed",
                              f"Unexpected {type(error).__name__}; see scheduler logs. Sender: {sender}.")
        return "failed" if permanent else "retry"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--max-messages", type=int, default=20)
    parser.add_argument("--reprocess-effective-date", action="append", default=[],
                        help="Replay retained Royal source through the current parser as an audited revision.")
    args = parser.parse_args()
    if os.getenv("ROYAL_GRAPH_MAILBOX", MAILBOX).lower() != MAILBOX:
        raise SystemExit("ROYAL_GRAPH_MAILBOX must be tim@midnightbe.com")
    repository = IntakeRepository(get_supabase_client())
    required = {key: os.getenv(key, "") for key in ("ROYAL_GRAPH_TENANT_ID", "ROYAL_GRAPH_CLIENT_ID", "ROYAL_GRAPH_CLIENT_SECRET")}
    if not all(required.values()):
        repository.notify("royal-email:configuration", "Royal email ingestion is not configured",
                          "Microsoft Graph tenant, client, or client-secret configuration is missing.")
        raise SystemExit("Royal Microsoft Graph credentials are not configured")
    allowed = {host.strip().lower() for host in os.getenv("ROYAL_DOWNLOAD_ALLOWED_DOMAINS", "").split(",") if host.strip()}
    graph = GraphClient(required["ROYAL_GRAPH_TENANT_ID"], required["ROYAL_GRAPH_CLIENT_ID"], required["ROYAL_GRAPH_CLIENT_SECRET"])
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=max(1, min(args.lookback_days, 30)))
    if args.reprocess_effective_date:
        remaining = set(args.reprocess_effective_date)
        results = []
        checkpoints = repository.replay_checkpoints(sorted(remaining))
        for checkpoint in checkpoints:
            effective = checkpoint.get("effective_date")
            if effective not in remaining:
                continue
            message = graph.message(MAILBOX, checkpoint["graph_message_id"])
            sender = str((((message.get("from") or {}).get("emailAddress") or {}).get("address")) or "").lower()
            if sender not in SENDERS:
                continue
            source_type, name, content, host = select_source(graph, message, allowed)
            with tempfile.TemporaryDirectory(prefix="mbop-royal-replay-") as directory:
                path = Path(directory) / name
                path.write_bytes(content)
                payload = parse_price_list(path, filename_reference_date=message.get("receivedDateTime"))
            if payload["effective_date"] != effective:
                continue
            if payload["status"] != "completed":
                raise IntakeError("validation_failed", f"Replay validation failed for {payload['effective_date']}")
            latest = repository.wholesale.latest_import_for_date(payload["supplier_key"], payload["effective_date"])
            if not latest:
                raise IntakeError("import_missing", f"No prior import exists for {payload['effective_date']}")
            result = repository.wholesale.apply_import(payload, latest["import_id"])
            supplier_id = repository.supplier()["supplier_id"]
            run_id = (None if result.get("already_imported") else
                      repository.queue_downstream(supplier_id, result["import_id"]))
            results.append({"effective_date": payload["effective_date"], "import_id": result["import_id"],
                            "already_imported": result.get("already_imported", False),
                            "rows_imported": (result.get("summary") or {}).get("rows_imported"),
                            "enrichment_run_id": run_id, "source_type": source_type,
                            "source_host": host})
            remaining.remove(payload["effective_date"])
            if not remaining:
                break
        if remaining:
            raise IntakeError("source_missing", f"No retained Royal message found for dates: {sorted(remaining)}")
        print({"status": "reprocessed", "results": results})
        return 0
    messages = graph.messages(MAILBOX, since)[:max(1, min(args.max_messages, 100))]
    counts: dict[str, int] = {}
    for message in messages:
        outcome = process_message(graph, repository, message, allowed)
        counts[outcome] = counts.get(outcome, 0) + 1
    repository.alert_if_stale(max(24, int(os.getenv("ROYAL_EMAIL_SILENCE_HOURS", "36"))))
    print({"mailbox": MAILBOX, "results": counts})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
