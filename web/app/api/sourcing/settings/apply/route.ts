import { execFile } from "child_process";
import path from "path";
import { promisify } from "util";
import { NextResponse } from "next/server";
import { supabase } from "../../_supabase";

const execFileAsync = promisify(execFile);

export const runtime = "nodejs";

export async function POST() {
  const { data: run, error } = await supabase
    .from("sourcing_runs")
    .select("sourcing_run_id,run_type,status,started_at")
    .order("started_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  if (!run?.sourcing_run_id) {
    return NextResponse.json({ applied: false, error: "No sourcing run found to refresh." }, { status: 404 });
  }

  const repoRoot = process.cwd().endsWith(`${path.sep}web`)
    ? path.resolve(process.cwd(), "..")
    : process.cwd();

  try {
    const { stdout, stderr } = await execFileAsync(
      "python",
      [
        "integrations/score_sourcing_opportunities.py",
        "--run-id",
        run.sourcing_run_id,
        "--update-existing",
      ],
      {
        cwd: repoRoot,
        timeout: 120000,
        maxBuffer: 1024 * 1024,
      },
    );

    return NextResponse.json({
      applied: true,
      runId: run.sourcing_run_id,
      stdout,
      stderr,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to apply sourcing settings.";
    return NextResponse.json({ applied: false, runId: run.sourcing_run_id, error: message }, { status: 500 });
  }
}
