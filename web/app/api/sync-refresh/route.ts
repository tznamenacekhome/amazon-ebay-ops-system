import { promises as fs } from "fs";
import path from "path";
import { spawn } from "child_process";
import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient, isCloudDeployment, isLocalJobExecutionEnabled, requireAdminApiToken } from "../_server";
import { runSchedulerGroupTask } from "../_awsScheduler";

export const runtime = "nodejs";

const ROOT_DIR = path.resolve(process.cwd(), "..");
const LOCK_PATH = path.join(ROOT_DIR, "logs", "run_all_syncs.lock");
const LOG_PATH = path.join(ROOT_DIR, "logs", "on_demand_sync.log");
const LOCK_STALE_HOURS = 10;

const TARGET_GROUPS: Record<string, string | null> = {
  purchases: "purchases",
  dashboard: "dashboard",
  "sales-orders": "sales-orders",
  "inventory-reconciliation": "reconciliation",
  repricing: "repricing",
  fba: "fba",
  "fba-pricing": "fba-pricing",
};

export async function GET(request: NextRequest) {
  const runId = request.nextUrl.searchParams.get("runId")?.trim();
  if (runId) {
    return NextResponse.json(await readRunStatus(runId));
  }

  const lock = await readActiveLock();
  return NextResponse.json({
    inProgress: Boolean(lock),
    lock,
  });
}

export async function POST(request: NextRequest) {
  const adminError = requireAdminApiToken(request);
  if (adminError) return adminError;

  const body = (await request.json().catch(() => ({}))) as { target?: string };
  const target = body.target || "";
  const group = TARGET_GROUPS[target];

  if (!(target in TARGET_GROUPS)) {
    return NextResponse.json({ error: "Unknown refresh target." }, { status: 400 });
  }

  if (group === null) {
    return NextResponse.json({
      status: "no_sync_required",
      message: "This screen is backed by MBOP workflow data only. The page data was reloaded.",
    });
  }

  const runId = `${target}-${new Date().toISOString().replace(/[:.]/g, "-")}`;

  if (isCloudDeployment()) {
    try {
      const task = await runSchedulerGroupTask({
        group,
        source: `mbop-web-on-demand-${target}`,
        job: target,
        runId,
      });
      return NextResponse.json({
        status: "started",
        target,
        group,
        runId,
        executionMode: "aws-ecs",
        taskArn: task.taskArn,
        message: `Started ${target} refresh in AWS. Check System Health for progress; page data will update after the scheduler task finishes.`,
      });
    } catch (error) {
      return NextResponse.json(
        {
          error: error instanceof Error ? error.message : `Failed to start ${target} refresh in AWS.`,
          target,
          group,
          executionMode: "aws-ecs",
        },
        { status: 500 },
      );
    }
  }

  if (!isLocalJobExecutionEnabled()) {
    return NextResponse.json(
      {
        error: "Local job execution is disabled and AWS scheduler execution is not active.",
        task: "on-demand sync refresh",
      },
      { status: 501 },
    );
  }

  const activeLock = await readActiveLock();
  if (activeLock) {
    return NextResponse.json(
      {
        status: "already_running",
        message: `A sync is already running (${activeLock.group || "unknown group"}).`,
        lock: activeLock,
      },
      { status: 409 },
    );
  }

  await fs.mkdir(path.dirname(LOG_PATH), { recursive: true });
  const command = [
    ".venv\\Scripts\\python.exe",
    "run_all_syncs.py",
    "--group",
    group,
    "--run-id",
    runId,
  ];
  const shellCommand = `${command.join(" ")} >> logs\\on_demand_sync.log 2>&1`;

  await fs.appendFile(
    LOG_PATH,
    `\n================================\nStarting on-demand ${target} refresh at ${new Date().toISOString()}\nCommand: ${shellCommand}\n`,
    "utf8",
  );

  const child = spawn("cmd.exe", ["/c", shellCommand], {
    cwd: ROOT_DIR,
    detached: true,
    stdio: "ignore",
    windowsHide: true,
  });
  child.unref();

  return NextResponse.json({
    status: "started",
    target,
    group,
    runId,
    message: `Started ${target} sync refresh.`,
  });
}

async function readRunStatus(runId: string) {
  try {
    const supabase = createServerSupabaseClient();
    const [{ data: runRows }, { data: jobRows }] = await Promise.all([
      supabase
        .from("scheduler_runs")
        .select("run_id,group_name,status,started_at,finished_at,runtime_seconds,error_summary")
        .eq("run_id", runId)
        .limit(1),
      supabase
        .from("scheduler_run_jobs")
        .select("job_name,status,started_at,finished_at,error_summary,rows_read,rows_inserted,rows_updated,rows_skipped,rate_limit_count,metadata")
        .eq("run_id", runId)
        .order("started_at", { ascending: true }),
    ]);
    const run = runRows?.[0] ?? null;
    const jobs = jobRows ?? [];
    return {
      found: Boolean(run),
      run,
      jobs,
      summary: summarizeRunJobs(jobs),
    };
  } catch (error) {
    return {
      found: false,
      error: error instanceof Error ? error.message : "Unable to read run status.",
    };
  }
}

type RunSummary = {
  rowsRead: number;
  rowsInserted: number;
  rowsUpdated: number;
  rowsSkipped: number;
  rateLimitCount: number;
  failures: number;
};

function summarizeRunJobs(jobs: Array<Record<string, unknown>>): RunSummary {
  return jobs.reduce<RunSummary>(
    (summary, job) => ({
      rowsRead: summary.rowsRead + numberValue(job.rows_read),
      rowsInserted: summary.rowsInserted + numberValue(job.rows_inserted),
      rowsUpdated: summary.rowsUpdated + numberValue(job.rows_updated),
      rowsSkipped: summary.rowsSkipped + numberValue(job.rows_skipped),
      rateLimitCount: summary.rateLimitCount + numberValue(job.rate_limit_count),
      failures: summary.failures + (job.status === "failed" || job.status === "blocked" ? 1 : 0),
    }),
    { rowsRead: 0, rowsInserted: 0, rowsUpdated: 0, rowsSkipped: 0, rateLimitCount: 0, failures: 0 } satisfies RunSummary,
  );
}

function numberValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

async function readActiveLock() {
  try {
    const raw = await fs.readFile(LOCK_PATH, "utf8");
    const lock = JSON.parse(raw) as {
      pid?: number;
      group?: string;
      run_id?: string;
      started_at?: string;
    };
    if (isStaleLock(lock.started_at)) {
      await fs.unlink(LOCK_PATH).catch(() => undefined);
      return null;
    }
    return lock;
  } catch {
    return null;
  }
}

function isStaleLock(startedAt?: string) {
  if (!startedAt) return true;
  const timestamp = Date.parse(startedAt);
  if (Number.isNaN(timestamp)) return true;
  return Date.now() - timestamp > LOCK_STALE_HOURS * 60 * 60 * 1000;
}
