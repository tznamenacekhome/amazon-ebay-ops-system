"""Shared purchase-ingestion reservation: API and scheduled workers use one RPC."""


def required(jobs):
    return any(job.name == 'eBay buyer purchases' for job in jobs)


def claim(client, run_id, task_arn=None):
    if client is None:
        raise RuntimeError('Purchase ingestion requires database concurrency protection')
    result = client.rpc('mbop_claim_purchase_ingestion', {
        'p_run_id': run_id, 'p_start': True, 'p_task_arn': task_arn,
    }).execute()
    row = result.data
    if not isinstance(row, dict) or 'acquired' not in row:
        raise RuntimeError('Invalid purchase-ingestion lock response')
    return row


def finish(client, run_id, status, finished_at):
    if client is None:
        return
    client.table('mbop_purchase_ingestion_requests').update({
        'status': 'succeeded' if status == 'ok' else 'failed',
        'completed_at': finished_at,
        'error_code': None if status == 'ok' else 'purchase_ingestion_failed',
    }).eq('run_id', run_id).in_('status', ['queued', 'running']).execute()
