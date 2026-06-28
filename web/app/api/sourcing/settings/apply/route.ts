import { execFile } from "child_process";
import path from "path";
import { promisify } from "util";
import { NextResponse } from "next/server";
import { supabase } from "../../_supabase";
import { isCloudDeployment, isLocalJobExecutionEnabled, requireAdminApiToken } from "../../../_server";
import { runSchedulerCommandTask } from "../../../_awsScheduler";

const execFileAsync = promisify(execFile);

export const runtime = "nodejs";

export async function POST(request: Request) {
  const adminError = requireAdminApiToken(request);
  if (adminError) return adminError;

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

  if (isCloudDeployment()) {
    try {
      const task = await runSchedulerCommandTask({
        command: [
          "python",
          "integrations/score_sourcing_opportunities.py",
          "--run-id",
          run.sourcing_run_id,
          "--update-existing",
        ],
        source: "mbop-web-sourcing-settings-apply",
        job: "sourcing-settings-apply",
        runId: run.sourcing_run_id,
      });

      return NextResponse.json({
        applied: true,
        status: "started",
        executionMode: "aws-ecs",
        runId: run.sourcing_run_id,
        taskArn: task.taskArn,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to apply sourcing settings in AWS.";
      return NextResponse.json({ applied: false, runId: run.sourcing_run_id, error: message }, { status: 500 });
    }
  }

  if (!isLocalJobExecutionEnabled()) {
    return NextResponse.json(
      {
        applied: false,
        error: "Local sourcing settings execution is disabled and AWS execution is not active.",
        runId: run.sourcing_run_id,
      },
      { status: 501 },
    );
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
