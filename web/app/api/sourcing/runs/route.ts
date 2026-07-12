import { NextRequest, NextResponse } from "next/server";
import { ECSClient, RunTaskCommand } from "@aws-sdk/client-ecs";
import { randomUUID } from "crypto";
import { execFile } from "child_process";
import { promises as fs } from "fs";
import path from "path";
import { promisify } from "util";
import { supabase } from "../_supabase";
import { isCloudDeployment, isLocalJobExecutionEnabled, requireAdminApiToken } from "../../_server";

export const runtime = "nodejs";

const execFileAsync = promisify(execFile);
const ROOT_DIR = path.resolve(process.cwd(), "..");
const LOG_PATH = path.join(ROOT_DIR, "logs", "sourcing_refresh.log");
const PYTHON = path.join(ROOT_DIR, ".venv", "Scripts", "python.exe");
const DEFAULT_SCHEDULER_SUBNETS = ["subnet-0acbbc29cdf301200", "subnet-07558cd00060ff69d"];
const DEFAULT_SCHEDULER_SECURITY_GROUPS = ["sg-0b05e7760083c5e31"];

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

  if (isCloudDeployment()) {
    try {
      const task = await runAwsSourcingTask(runId, runType);
      return NextResponse.json({
        run: data,
        status: "started",
        executionMode: "aws-ecs",
        taskArn: task.taskArn,
        nextSteps,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to start AWS sourcing task.";
      await supabase
        .from("sourcing_runs")
        .update({
          status: "failed",
          completed_at: new Date().toISOString(),
          error_message: message,
        })
        .eq("sourcing_run_id", runId);
      return NextResponse.json({ error: message, run: data }, { status: 500 });
    }
  }

  if (!isLocalJobExecutionEnabled()) {
    return NextResponse.json(
      {
        error: "Local sourcing execution is disabled and AWS sourcing execution is not configured.",
        task: "sourcing Python run",
      },
      { status: 501 },
    );
  }

  try {
    await fs.mkdir(path.dirname(LOG_PATH), { recursive: true });
    await appendLog(`\n================================\nStarting sourcing ${runType} run ${runId} at ${new Date().toISOString()}\n`);
    await runStep("Run quota-based sourcing workflow", [
      "integrations/run_sourcing_workflow.py",
      "--run-id",
      runId,
      "--run-type",
      runType,
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

export async function runAwsSourcingTask(runId: string, runType: "recent_sales" | "full_listings", continueRun = false) {
  const client = new ECSClient({ region: process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || "us-west-2" });
  const cluster = process.env.MBOP_SCHEDULER_CLUSTER || "mbop-cluster1";
  const taskDefinition = process.env.MBOP_SCHEDULER_TASK_DEFINITION || "mbop-scheduler-task";
  const containerName = process.env.MBOP_SCHEDULER_CONTAINER || "mbop-scheduler";
  const subnetIds = csvEnv("MBOP_SCHEDULER_SUBNET_IDS");
  const securityGroupIds = csvEnv("MBOP_SCHEDULER_SECURITY_GROUP_IDS");

  const subnets = subnetIds.length ? subnetIds : DEFAULT_SCHEDULER_SUBNETS;
  const securityGroups = securityGroupIds.length ? securityGroupIds : DEFAULT_SCHEDULER_SECURITY_GROUPS;

  const response = await client.send(new RunTaskCommand({
    cluster,
    taskDefinition,
    launchType: "FARGATE",
    count: 1,
    platformVersion: "LATEST",
    networkConfiguration: {
      awsvpcConfiguration: {
        subnets,
        securityGroups,
        assignPublicIp: "ENABLED",
      },
    },
    overrides: {
      cpu: "1024",
      memory: "4096",
      containerOverrides: [
        {
          name: containerName,
          command: [
            "python",
            "integrations/run_sourcing_workflow.py",
            "--run-id",
            runId,
            "--run-type",
            runType,
            ...(continueRun ? ["--continue-run"] : []),
          ],
          environment: [
            { name: "SCHEDULER_TRIGGER_SOURCE", value: "web-on-demand" },
            { name: "EVENTBRIDGE_SCHEDULE_NAME", value: "mbop-web-on-demand-sourcing" },
          ],
        },
      ],
    },
    tags: [
      { key: "mbop:source", value: "web-on-demand" },
      { key: "mbop:job", value: "sourcing" },
      { key: "mbop:sourcing-run-id", value: runId },
      { key: "mbop:sourcing-run-type", value: runType },
    ],
  }));

  const failure = response.failures?.[0];
  if (failure) {
    throw new Error(`ECS RunTask failed: ${failure.arn ?? failure.reason ?? "unknown failure"} ${failure.detail ?? ""}`.trim());
  }
  const task = response.tasks?.[0];
  if (!task?.taskArn) {
    throw new Error("ECS RunTask did not return a task ARN.");
  }
  return task;
}

function csvEnv(name: string) {
  return (process.env[name] || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
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
