import "server-only";

import { createClient } from "@supabase/supabase-js";
import { NextResponse } from "next/server";

function normalizedEnv(name: string) {
  const value = process.env[name];
  return typeof value === "string" ? value.trim() : "";
}

function isTruthy(value: string) {
  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}

function isFalsey(value: string) {
  return ["0", "false", "no", "off"].includes(value.toLowerCase());
}

export function isCloudDeployment() {
  const cloudDeployment = normalizedEnv("CLOUD_DEPLOYMENT");
  const localSyncEnabled = normalizedEnv("LOCAL_SYNC_ENABLED");

  return isTruthy(cloudDeployment) || isFalsey(localSyncEnabled);
}

export function isLocalJobExecutionEnabled() {
  return !isCloudDeployment();
}

export function requiredEnv(name: string) {
  const value = normalizedEnv(name);
  if (!value) {
    throw new Error(`Missing required server environment variable: ${name}`);
  }
  return value;
}

export function createServerSupabaseClient() {
  return createClient(
    requiredEnv("SUPABASE_URL"),
    requiredEnv("SUPABASE_SERVICE_ROLE_KEY"),
  );
}

export function localJobDisabledResponse(task: string, status: 501 | 409 = 501) {
  return NextResponse.json(
    {
      error: "Local job execution is disabled in cloud deployment.",
      task,
      cloudDeployment: true,
      details:
        "Scheduled Python jobs are still expected to run locally during Phase 1.",
    },
    { status },
  );
}

export function localFileSignalUnavailable(source: string) {
  return {
    lastRunAt: null,
    lastUpdatedAt: null,
    source,
    stats: [],
    statusOverride: "skipped" as const,
    message: "Local file signal unavailable in cloud deployment.",
  };
}

export function requireAdminApiToken(request: Request) {
  const expected = normalizedEnv("MBOP_ADMIN_API_TOKEN");
  if (!expected) return null;

  const bearer = request.headers.get("authorization")?.match(/^Bearer\s+(.+)$/i)?.[1]?.trim();
  const header = request.headers.get("x-mbop-admin-token")?.trim();

  if (bearer === expected || header === expected) return null;

  return NextResponse.json(
    {
      error: "Admin API token required.",
      details:
        "Set the x-mbop-admin-token header or Authorization: Bearer token for this privileged endpoint.",
    },
    { status: 401 },
  );
}
