"""Bounded, fail-closed capacity gate for catalog work; never retries writes."""
import os
import time

import requests

try:
    from .scheduler_diagnostics import emit, parse_pressure
except ImportError:  # Direct integration script entry point.
    from scheduler_diagnostics import emit, parse_pressure


class DatabasePressureError(RuntimeError):
    pass


def pressure_reason(values):
    required = ('pg_up', 'node_memory_MemAvailable_bytes', 'node_memory_MemTotal_bytes',
                'node_memory_SwapFree_bytes', 'node_memory_SwapTotal_bytes',
                'node_filesystem_avail_bytes', 'node_filesystem_size_bytes')
    if any(key not in values for key in required):
        return 'missing_metrics'
    if values['pg_up'] != 1:
        return 'database_unavailable'
    if values['node_memory_MemAvailable_bytes'] < max(256 * 1024**2, values['node_memory_MemTotal_bytes'] * .15):
        return 'low_available_memory'
    if values['node_memory_SwapTotal_bytes'] and values['node_memory_SwapFree_bytes'] < values['node_memory_SwapTotal_bytes'] * .25:
        return 'low_swap_headroom'
    if values['node_filesystem_avail_bytes'] < max(1024**3, values['node_filesystem_size_bytes'] * .15):
        return 'low_disk_headroom'
    return None


def wait_for_database(supabase, *, attempts=11, interval=30):
    """Require fresh capacity metrics and a tiny successful read before proceeding."""
    url = os.environ.get('SUPABASE_URL', '').rstrip('/')
    key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
    if url != 'https://froeucjkcepuhgwisped.supabase.co' or not key:
        raise DatabasePressureError('Missing or unexpected Supabase configuration')
    for attempt in range(attempts):
        try:
            response = requests.get(url + '/customer/v1/privileged/metrics', auth=('username', key), timeout=8)
            response.raise_for_status()
            values = parse_pressure(response.text)
            reason = pressure_reason(values)
            if reason is None:
                supabase.table('sourcing_runs').select('sourcing_run_id').limit(1).execute()
                emit('database_guard_ready', values=values)
                return
        except Exception as error:
            reason = type(error).__name__
        emit('database_guard_wait', reason=reason, attempt=attempt + 1)
        if attempt + 1 < attempts:
            time.sleep(interval)
    raise DatabasePressureError('Catalog paused: database capacity did not recover within the bounded wait')


def guard_if_enabled(supabase):
    if os.environ.get('MBOP_CATALOG_DATABASE_GUARD') == '1':
        wait_for_database(supabase)
