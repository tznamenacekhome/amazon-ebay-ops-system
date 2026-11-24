import { NextRequest, NextResponse } from 'next/server';
import { randomUUID } from 'crypto';
import { spawn } from 'child_process';
import path from 'path';
import { supabase } from '../_supabase';
import { requireAdminApiToken, isCloudDeployment, isLocalJobExecutionEnabled } from '../../_server';
import { runAwsSourcingTask } from '../runs/route';
import { GET as opportunities } from '../opportunities/route';
import { presentationCounts } from './presentation';
import { ebayQuotaOverview } from '../ebayQuota';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
const RUN_FIELDS = 'run_id,status,started_at,completed_at,heartbeat_at,error_summary,summary,next_retry_at,paused_resource';
const TAB_FIELDS = 'tab_id,run_id,sheet_id,tab_name,status,rows_found,summary,error_summary,completed_at';

export async function POST(request: NextRequest) {
  const denied = requireAdminApiToken(request);
  if (denied) return denied;
  let runId: string | undefined;
  try {
    if (!isCloudDeployment() && !isLocalJobExecutionEnabled()) return NextResponse.json({ error: 'Manual sourcing execution is disabled.' }, { status: 503 });
    const begun = await supabase.rpc('flipmine_begin', { p_run: randomUUID() });
    if (begun.error) throw begun.error;
    runId = begun.data.run_id;
    if (begun.data.launch) {
      if (isCloudDeployment()) {
        const task = await runAwsSourcingTask(runId!, 'flipmine');
        const saved = await supabase.from('sourcing_flipmine_runs').update({ task_arn: task.taskArn }).eq('run_id', runId);
        if (saved.error) throw saved.error;
      } else {
        const root = path.resolve(process.cwd(), '..');
        await new Promise<void>((resolve, reject) => {
          const child = spawn(path.join(root, '.venv', 'Scripts', 'python.exe'), ['integrations/import_flipmine.py', '--run-id', runId!],
            { cwd: root, detached: true, windowsHide: true, stdio: 'ignore' });
          child.once('error', reject);
          child.once('spawn', () => { child.unref(); resolve(); });
        });
      }
    }
    return NextResponse.json({ runId, status: begun.data.status ?? 'running', started: begun.data.launch });
  } catch {
    if (runId) await supabase.from('sourcing_flipmine_runs').update({ status: 'failed', completed_at: new Date().toISOString(), error_summary: 'Could not start import worker; retry the manual import.' }).eq('run_id', runId).eq('status', 'running');
    return NextResponse.json({ error: 'Could not start Flipmine import. Check the worker configuration and migration.' }, { status: 503 });
  }
}

export async function GET(request: NextRequest) {
  try {
    const result = await supabase.from('sourcing_flipmine_runs').select(RUN_FIELDS).order('started_at', { ascending: false }).limit(10);
    const quota = await ebayQuotaOverview();
    if (result.error) throw result.error;
    const runs = result.data ?? [];
    const run = runs[0];
    if (!run) return NextResponse.json({ run: null, tabs: [], history: [], quota });
    if (run.status === 'running' && Date.parse(run.heartbeat_at) < Date.now() - 90 * 60_000) {
      await supabase.from('sourcing_flipmine_runs').update({ status: 'failed', error_summary: 'Worker interrupted; Import Flipmine resumes retained rows.' }).eq('run_id', run.run_id).eq('status', 'running').eq('heartbeat_at', run.heartbeat_at);
      run.status = 'failed'; run.error_summary = 'Worker interrupted; Import Flipmine resumes retained rows.';
    }
    const tabResult = await supabase.from('sourcing_flipmine_tabs').select(TAB_FIELDS).eq('run_id', run.run_id).order('sheet_id').limit(1000);
    if (tabResult.error) throw tabResult.error;
    const tabs = tabResult.data ?? [];
    if (tabs.length) {
      const live = await supabase.rpc('flipmine_progress_counts', { p_tabs: tabs.map(t => t.tab_id) });
      if (live.error) throw live.error;
      for (const tab of tabs) {
        const counts = live.data?.find((r: { tab_id: string }) => r.tab_id === tab.tab_id)?.counts;
        if (!counts || counts.rows !== tab.rows_found) throw new Error('Persisted candidate totals do not reconcile');
        tab.summary = { ...tab.summary, ...counts };
      }
    }
    if (run.status !== 'running') {
      for (const tab of tabs.filter(t => t.status === 'evaluated')) {
        try {
          const counts = await presentationCounts(tab.tab_id, url => opportunities(new NextRequest(new URL(url, request.url))));
          const completed = await supabase.rpc('flipmine_complete_tab', { p_tab: tab.tab_id, p_summary: counts });
          if (completed.error || completed.data !== true) throw completed.error ?? new Error('Tab claimed by another run');
          tab.status = 'completed'; tab.summary = { ...tab.summary, ...counts };
        } catch { tab.error_summary = 'Evaluation retained. Presentation counts unavailable; refresh to retry.'; }
      }
      if (run.status === 'evaluated' && tabs.length && tabs.every(t => t.status === 'completed')) {
        const summary = { ...run.summary, completedTabs: tabs.length };
        const saved = await supabase.from('sourcing_flipmine_runs').update({ status: 'completed', summary, completed_at: new Date().toISOString() }).eq('run_id', run.run_id).eq('status', 'evaluated');
        if (saved.error) throw saved.error;
        run.status = 'completed'; run.summary = summary;
      }
    }
    return NextResponse.json({ run, tabs, history: runs.slice(1), quota }, { headers: { 'Cache-Control': 'no-store' } });
  } catch {
    return NextResponse.json({ error: 'Flipmine status unavailable. Check database connectivity and the Flipmine migration.' }, { status: 503 });
  }
}
