"""Bounded operator maintenance: verified S3 backup before any finance payload update.

Dry-run by default. Keeps seven days inline. No balances, dates, or source
transaction values are changed; archived JSON is recoverable with --restore-id.
"""
import argparse
import datetime as dt
import hashlib
import json
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integrations'))
import boto3
from dotenv import dotenv_values
from supabase import create_client
from finance_payload_archive import (ACCOUNT_ID, archive_payload, canonical_bytes,
                                     is_archived, restore_payload)

TABLE = 'amazon_finance_balance_snapshots'
PK = 'amazon_finance_balance_snapshot_id'


def fingerprint(row):
    return hashlib.sha256(canonical_bytes({k: v for k, v in row.items()
                                         if k != 'raw_transactions_json'})).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--limit', type=int, default=25)
    parser.add_argument('--workers', type=int, choices=(1, 2, 3), default=1)
    parser.add_argument('--restore-id')
    args = parser.parse_args()
    if not 1 <= args.limit <= 300:
        parser.error('--limit must be 1..300')
    cfg = dotenv_values(ROOT / '.env.local')
    if cfg['SUPABASE_URL'].rstrip('/') != 'https://froeucjkcepuhgwisped.supabase.co':
        raise RuntimeError('Unexpected Supabase target')
    session = boto3.Session(profile_name='mbop-admin', region_name='us-west-2')
    if session.client('sts').get_caller_identity()['Account'] != ACCOUNT_ID:
        raise RuntimeError('Unexpected AWS account')
    s3 = session.client('s3')
    db = create_client(cfg['SUPABASE_URL'], cfg['SUPABASE_SERVICE_ROLE_KEY'])
    db.table(TABLE).select(PK).limit(1).execute()
    if args.restore_id:
        row = db.table(TABLE).select('*').eq(PK, args.restore_id).single().execute().data
        ref = row['raw_transactions_json']
        if not is_archived(ref):
            raise RuntimeError('Row does not contain an archive reference')
        payload = restore_payload(s3, ref)
        print(json.dumps({'restore_id': args.restore_id, 'verified': True, 'apply': args.apply}))
        if args.apply:
            db.table(TABLE).update({'raw_transactions_json': payload}).eq(PK, args.restore_id).execute()
            result = db.table(TABLE).select('*').eq(PK, args.restore_id).single().execute().data
            if result['raw_transactions_json'] != payload or fingerprint(row) != fingerprint(result):
                raise RuntimeError('Restore verification failed')
        return
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).isoformat()
    rows = (db.table(TABLE).select(PK + ',captured_at')
            .lt('captured_at', cutoff).is_('raw_transactions_json->>archive_format', 'null')
            .order('captured_at').limit(args.limit).execute().data)
    print(json.dumps({'eligible_batch': len(rows), 'cutoff': cutoff, 'apply': args.apply}), flush=True)
    if not args.apply:
        return
    out = ROOT / 'logs/diagnostics/finance-archive-20260910'
    out.mkdir(parents=True, exist_ok=True)
    manifest_lock = threading.Lock()
    stopped = threading.Event()
    def archive_entry(entry):
        # Independent clients avoid sharing mutable PostgREST builders across threads.
        db = create_client(cfg['SUPABASE_URL'], cfg['SUPABASE_SERVICE_ROLE_KEY'])
        row = db.table(TABLE).select('*').eq(PK, entry[PK]).single().execute().data
        payload = row.get('raw_transactions_json')
        if payload is None or is_archived(payload):
            return
        backup = archive_payload(s3, row, prefix='finance-snapshot-backups/v1/')
        reference = archive_payload(s3, payload)
        reference['snapshot_backup'] = backup
        record = {'id': row[PK], 'unchanged_fields_sha256': fingerprint(row), 'reference': reference}
        # Recovery reference reaches durable storage AND a local manifest before mutation.
        with manifest_lock:
            with (out / 'manifest.jsonl').open('a', encoding='utf-8') as manifest:
                manifest.write(json.dumps(record) + '\n')
        # Snapshot rows are append-only in the importer; reject already archived rows.
        db.table(TABLE).update({'raw_transactions_json': reference}).eq(PK, row[PK]).is_(
            'raw_transactions_json->>archive_format', 'null').execute()
        after = db.table(TABLE).select('*').eq(PK, row[PK]).single().execute().data
        if fingerprint(after) != fingerprint(row) or after['raw_transactions_json'] != reference:
            raise RuntimeError('Post-update verification failed; stop and use manifest')
        print(json.dumps({'id': row[PK],
                          'archived_bytes': reference['uncompressed_bytes'], 'verified': True}), flush=True)
        time.sleep(0.25)
    def process_entry(entry):
        if stopped.is_set():
            return
        try:
            archive_entry(entry)
        except Exception:
            # In-flight rows finish their atomic, backed-up updates; no new rows start.
            stopped.set()
            raise
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        # At most three payloads in memory/on the wire; identifiers are bounded above.
        list(pool.map(process_entry, rows))


if __name__ == '__main__':
    main()
