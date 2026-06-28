import "server-only";

import { ECSClient, RunTaskCommand } from "@aws-sdk/client-ecs";

const DEFAULT_SCHEDULER_SUBNETS = ["subnet-0acbbc29cdf301200", "subnet-07558cd00060ff69d"];
const DEFAULT_SCHEDULER_SECURITY_GROUPS = ["sg-0b05e7760083c5e31"];

export type SchedulerTaskRequest = {
  group: string;
  source: string;
  job: string;
  runId?: string;
};

export async function runSchedulerGroupTask({ group, source, job, runId }: SchedulerTaskRequest) {
  return runSchedulerCommandTask({
    command: ["python", "run_all_syncs.py", "--group", group],
    source,
    job,
    group,
    runId,
  });
}

export type SchedulerCommandTaskRequest = {
  command: string[];
  source: string;
  job: string;
  group?: string;
  runId?: string;
};

export async function runSchedulerCommandTask({
  command,
  source,
  job,
  group,
  runId,
}: SchedulerCommandTaskRequest) {
  const client = new ECSClient({ region: process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || "us-west-2" });
  const cluster = process.env.MBOP_SCHEDULER_CLUSTER || "mbop-cluster1";
  const taskDefinition = process.env.MBOP_SCHEDULER_TASK_DEFINITION || "mbop-scheduler-task";
  const containerName = process.env.MBOP_SCHEDULER_CONTAINER || "mbop-scheduler";
  const subnets = csvEnv("MBOP_SCHEDULER_SUBNET_IDS", DEFAULT_SCHEDULER_SUBNETS);
  const securityGroups = csvEnv("MBOP_SCHEDULER_SECURITY_GROUP_IDS", DEFAULT_SCHEDULER_SECURITY_GROUPS);

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
          command,
          environment: [
            { name: "SCHEDULER_TRIGGER_SOURCE", value: source },
            { name: "EVENTBRIDGE_SCHEDULE_NAME", value: source },
          ],
        },
      ],
    },
    tags: [
      { key: "mbop:source", value: source },
      { key: "mbop:job", value: job },
      ...(group ? [{ key: "mbop:group", value: group }] : []),
      ...(runId ? [{ key: "mbop:run-id", value: runId }] : []),
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

function csvEnv(name: string, fallback: string[]) {
  const values = (process.env[name] || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  return values.length ? values : fallback;
}
