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
  const runType = "daily_catalog_sourcing";
  const execute = body.execute === true;
  const runId = randomUUID();

  const nextSteps = [
    `python integrations/run_daily_catalog_sourcing.py --run-id ${runId}`,
  ];

  if (!execute) {
    return NextResponse.json({
      run: { sourcing_run_id: runId, run_type: runType, status: "planned" },
      nextSteps,
    });
  }

  if (isCloudDeployment()) {
    try {
      const task = await runAwsSourcingTask(runId, runType);
      return NextResponse.json({
        run: { sourcing_run_id: runId, run_type: runType, status: "planned" },
        status: "started",
        executionMode: "aws-ecs",
        taskArn: task.taskArn,
        nextSteps,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to start AWS sourcing task.";
      await supabase
        .from("sourcing_runs")
        .upsert({
          sourcing_run_id: runId,
          run_type: runType,
          status: "failed",
          started_at: new Date().toISOString(),
          completed_at: new Date().toISOString(),
          error_message: message,
        }, { onConflict: "sourcing_run_id" });
      return NextResponse.json({ error: message, run: { sourcing_run_id: runId, run_type: runType } }, { status: 500 });
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
    await runStep("Run unified daily sourcing workflow", [
      "integrations/run_daily_catalog_sourcing.py",
      "--run-id",
      runId,
    ]);
    await appendLog(`Completed sourcing ${runType} run ${runId} at ${new Date().toISOString()}\n`);

    const { data: completedRun } = await supabase
      .from("sourcing_runs")
      .select("*")
      .eq("sourcing_run_id", runId)
      .single();

    return NextResponse.json({
      run: completedRun ?? { sourcing_run_id: runId, run_type: runType, status: "completed" },
      status: "completed",
      nextSteps,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Sourcing run failed.";
    await appendLog(`FAILED sourcing ${runType} run ${runId}: ${message}\n`);
    await supabase
      .from("sourcing_runs")
      .upsert({
        sourcing_run_id: runId,
        run_type: runType,
        status: "failed",
        started_at: new Date().toISOString(),
        completed_at: new Date().toISOString(),
        error_message: message,
      }, { onConflict: "sourcing_run_id" });

    return NextResponse.json({ error: message, run: { sourcing_run_id: runId, run_type: runType } }, { status: 500 });
  }
}

export async function runAwsSourcingTask(runId: string, runType: "recent_sales" | "full_listings" | "daily_catalog_sourcing", continueRun = false) {
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
          command: sourcingTaskCommand(runId, runType, continueRun),
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

function sourcingTaskCommand(runId: string, runType: "recent_sales" | "full_listings" | "daily_catalog_sourcing", continueRun: boolean) {
  if (runType === "daily_catalog_sourcing" && !continueRun) {
    return ["python", "integrations/run_daily_catalog_sourcing.py", "--run-id", runId];
  }
  return [
    "python",
    "integrations/run_sourcing_workflow.py",
    "--run-id",
    runId,
    "--run-type",
    runType === "daily_catalog_sourcing" ? "full_listings" : runType,
    ...(continueRun ? ["--continue-run"] : []),
  ];
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
