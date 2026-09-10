"""Lossless private archive for finance source payloads; never for balance fields."""
from __future__ import annotations

import gzip
import hashlib
import json
import os

ACCOUNT_ID = "297464765814"
BUCKET = "mbop-finance-archive-297464765814-us-west-2"
PREFIX = "finance-transactions/v1/"
FORMAT = "mbop.finance-transactions.gzip.v1"


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def is_archived(value):
    return isinstance(value, dict) and value.get("archive_format") == FORMAT


def archive_payload(s3, payload, *, bucket=BUCKET, prefix=PREFIX):
    if bucket != BUCKET or prefix not in (PREFIX, "finance-snapshot-backups/v1/"):
        raise ValueError("Unexpected finance archive destination")
    raw = canonical_bytes(payload)
    digest = hashlib.sha256(raw).hexdigest()
    key = prefix + digest + ".json.gz"
    s3.put_object(Bucket=bucket, Key=key, Body=gzip.compress(raw, mtime=0),
                  ContentType="application/gzip", ServerSideEncryption="AES256",
                  ExpectedBucketOwner=ACCOUNT_ID, Metadata={"sha256": digest})
    ref = {"archive_format": FORMAT, "bucket": bucket, "key": key,
           "sha256": digest, "uncompressed_bytes": len(raw)}
    # Verify the actual stored object before allowing an inline payload to be replaced.
    if restore_payload(s3, ref) != payload:
        raise ValueError("Finance archive round-trip mismatch")
    return ref


def restore_payload(s3, reference):
    if (not is_archived(reference) or reference.get("bucket") != BUCKET
            or not any(str(reference.get("key", "")).startswith(p)
                       for p in (PREFIX, "finance-snapshot-backups/v1/"))):
        raise ValueError("Unexpected finance archive reference")
    response = s3.get_object(Bucket=BUCKET, Key=reference["key"],
                             ExpectedBucketOwner=ACCOUNT_ID)
    body = response["Body"]
    try:
        raw = gzip.decompress(body.read())
    finally:
        body.close()
    if (len(raw) != reference["uncompressed_bytes"]
            or hashlib.sha256(raw).hexdigest() != reference["sha256"]):
        raise ValueError("Finance archive integrity check failed")
    return json.loads(raw)


def archive_new_snapshot(snapshot, *, s3=None):
    """Opt-in writer; caller keeps inline source data if archive service fails."""
    if os.environ.get("MBOP_FINANCE_PAYLOAD_ARCHIVE") != "1":
        return snapshot
    payload = snapshot.get("raw_transactions_json")
    if payload is None or is_archived(payload):
        return snapshot
    if s3 is None:
        import boto3
        s3 = boto3.client("s3", region_name="us-west-2")
    return {**snapshot, "raw_transactions_json": archive_payload(s3, payload)}
