import { promises as fs } from "fs";
import path from "path";
import { spawn } from "child_process";
import { NextRequest, NextResponse } from "next/server";

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

export async function GET() {
  const lock = await readActiveLock();
  return NextResponse.json({
    inProgress: Boolean(lock),
    lock,
  });
}

export async function POST(request: NextRequest) {
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
  const runId = `${target}-${new Date().toISOString().replace(/[:.]/g, "-")}`;
  const command = [
    ".venv\\Scripts\\python.exe",
    "run_all_syncs.py",
    "--group",
    group,
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
