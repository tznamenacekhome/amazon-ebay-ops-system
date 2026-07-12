import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient, requireAdminApiToken } from "../../../../_server";
import { runAwsSourcingTask } from "../../route";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest, { params }: { params: Promise<{ runId: string }> }) {
  const adminError = requireAdminApiToken(request);
  if (adminError) return adminError;

  const { runId } = await params;
  const supabase = createServerSupabaseClient();
  const { data: run, error } = await supabase
    .from("sourcing_runs")
    .select("sourcing_run_id,run_type,status")
    .eq("sourcing_run_id", runId)
    .maybeSingle();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  if (!run?.sourcing_run_id) return NextResponse.json({ error: "Sourcing run not found." }, { status: 404 });
  if (run.run_type !== "recent_sales" && run.run_type !== "full_listings") {
    return NextResponse.json({ error: "Unsupported sourcing run type." }, { status: 400 });
  }
  if (run.status === "running" || run.status === "planned") {
    return NextResponse.json({ error: "This sourcing run is already running." }, { status: 409 });
  }

  await supabase
    .from("sourcing_runs")
    .update({ status: "running", completed_at: null, error_message: null })
    .eq("sourcing_run_id", runId);

  try {
    const task = await runAwsSourcingTask(run.sourcing_run_id, run.run_type, true);
    return noStoreJson({
      runId: run.sourcing_run_id,
      status: "started",
      executionMode: "aws-ecs",
      taskArn: task.taskArn,
    });
  } catch (taskError) {
    const message = taskError instanceof Error ? taskError.message : "Failed to start AWS sourcing continuation.";
    await supabase
      .from("sourcing_runs")
      .update({ status: "failed", completed_at: new Date().toISOString(), error_message: message })
      .eq("sourcing_run_id", run.sourcing_run_id);
    return noStoreJson({ error: message }, { status: 500 });
  }
}

function noStoreJson(body: unknown, init?: ResponseInit) {
  const response = NextResponse.json(body, init);
  response.headers.set("Cache-Control", "no-store, no-cache, must-revalidate, proxy-revalidate");
  response.headers.set("Pragma", "no-cache");
  response.headers.set("Expires", "0");
  return response;
}
