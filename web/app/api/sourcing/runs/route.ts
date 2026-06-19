import { NextRequest, NextResponse } from "next/server";
import { randomUUID } from "crypto";
import { execFile } from "child_process";
import { promises as fs } from "fs";
import path from "path";
import { promisify } from "util";
import { supabase } from "../_supabase";
import { isLocalJobExecutionEnabled, localJobDisabledResponse, requireAdminApiToken } from "../../_server";

export const runtime = "nodejs";

const execFileAsync = promisify(execFile);
const ROOT_DIR = path.resolve(process.cwd(), "..");
const LOG_PATH = path.join(ROOT_DIR, "logs", "sourcing_refresh.log");
const PYTHON = path.join(ROOT_DIR, ".venv", "Scripts", "python.exe");

export async function POST(request: NextRequest) {
  const adminError = requireAdminApiToken(request);
  if (adminError) return adminError;

  const body = await request.json().catch(() => ({}));
  const runType = body.runType === "full_listings" ? "full_listings" : "recent_sales";
  const execute = body.execute === true;
  const runId = randomUUID();

  const { data: settings } = await supabase
    .from("sourcing_settings")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  const { data, error } = await supabase
    .from("sourcing_runs")
    .insert({
      sourcing_run_id: runId,
      run_type: runType,
      status: "planned",
      started_at: new Date().toISOString(),
      settings_snapshot: settings ?? {},
    })
    .select("*")
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  const nextSteps = [
    `python integrations/build_sourcing_seed_asins.py --mode ${runType} --run-id ${runId}`,
    `python integrations/ebay_sourcing_search.py --run-id ${runId}`,
    `python integrations/score_sourcing_opportunities.py --run-id ${runId}`,
  ];

  if (!execute) {
    return NextResponse.json({
      run: data,
      nextSteps,
    });
  }

  if (!isLocalJobExecutionEnabled()) {
    return localJobDisabledResponse("sourcing Python run");
  }

  try {
    await fs.mkdir(path.dirname(LOG_PATH), { recursive: true });
    await appendLog(`\n================================\nStarting sourcing ${runType} run ${runId} at ${new Date().toISOString()}\n`);
    await runStep("Build sourcing seed ASINs", [
      "integrations/build_sourcing_seed_asins.py",
      "--mode",
      runType,
      "--limit",
      "250",
      "--run-id",
      runId,
      "--replace-run",
    ]);
    await runStep("Search eBay sourcing candidates", [
      "integrations/ebay_sourcing_search.py",
      "--run-id",
      runId,
      "--limit",
      "50",
      "--max-results-per-asin",
      "10",
    ]);
    await runStep("Score sourcing opportunities", [
      "integrations/score_sourcing_opportunities.py",
      "--run-id",
      runId,
      "--replace-run",
    ]);
    await appendLog(`Completed sourcing ${runType} run ${runId} at ${new Date().toISOString()}\n`);

    const { data: completedRun } = await supabase
      .from("sourcing_runs")
      .select("*")
      .eq("sourcing_run_id", runId)
      .single();

    return NextResponse.json({
      run: completedRun ?? data,
      status: "completed",
      nextSteps,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Sourcing run failed.";
    await appendLog(`FAILED sourcing ${runType} run ${runId}: ${message}\n`);
    await supabase
      .from("sourcing_runs")
      .update({
        status: "failed",
        completed_at: new Date().toISOString(),
      })
      .eq("sourcing_run_id", runId);

    return NextResponse.json({ error: message, run: data }, { status: 500 });
  }
}

async function runStep(label: string, args: string[]) {
  await appendLog(`\n--- ${label}: ${PYTHON} ${args.join(" ")} ---\n`);
  try {
    const result = await execFileAsync(PYTHON, args, {
      cwd: ROOT_DIR,
      windowsHide: true,
      maxBuffer: 1024 * 1024 * 10,
    });
    if (result.stdout) await appendLog(result.stdout);
    if (result.stderr) await appendLog(result.stderr);
  } catch (error) {
    const output = commandOutput(error);
    if (output) await appendLog(output);
    throw new Error(`${label} failed. See logs/sourcing_refresh.log for details.`);
  }
}

function commandOutput(error: unknown) {
  if (!error || typeof error !== "object") return "";
  const value = error as { stdout?: string; stderr?: string };
  return `${value.stdout ?? ""}${value.stderr ?? ""}`;
}

async function appendLog(text: string) {
  await fs.appendFile(LOG_PATH, text, "utf8");
}
