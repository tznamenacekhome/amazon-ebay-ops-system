import crypto from "crypto";
import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

export const runtime = "nodejs";

const supabaseUrl = process.env.SUPABASE_URL!;
const supabaseServiceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;
const webhookSecret = process.env.EASYPOST_WEBHOOK_SECRET;
const timestampToleranceMinutes = Number(
  process.env.EASYPOST_WEBHOOK_TOLERANCE_MINUTES ?? "1"
);

const supabase = createClient(supabaseUrl, supabaseServiceRoleKey);

type EasyPostTracker = {
  id?: string;
  object?: string;
  tracking_code?: string;
  carrier?: string | null;
  status?: string | null;
  est_delivery_date?: string | null;
  public_url?: string | null;
  tracking_details?: Array<{
    message?: string | null;
    status?: string | null;
    datetime?: string | null;
    tracking_location?: unknown;
  }>;
};

type EasyPostEvent = {
  id?: string;
  description?: string;
  result?: EasyPostTracker;
};

export async function POST(request: Request) {
  const rawBody = await request.text();

  if (!webhookSecret) {
    return NextResponse.json(
      { error: "EASYPOST_WEBHOOK_SECRET is not configured" },
      { status: 500 }
    );
  }

  const validationError = validateEasyPostSignature(request, rawBody);

  if (validationError) {
    return NextResponse.json({ error: validationError }, { status: 401 });
  }

  let event: EasyPostEvent;

  try {
    event = JSON.parse(rawBody);
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  if (event.description !== "tracker.updated") {
    return NextResponse.json({ received: true, ignored: true });
  }

  const tracker = event.result;

  if (!tracker || tracker.object !== "Tracker") {
    return NextResponse.json({ received: true, ignored: true });
  }

  const payload = buildShipmentUpdatePayload(tracker);

  if (!payload) {
    return NextResponse.json({ received: true, ignored: true });
  }

  const updatedByTrackerId = tracker.id
    ? await supabase
        .from("inbound_shipments")
        .update(payload)
        .eq("easypost_tracker_id", tracker.id)
        .select("inbound_shipment_id")
    : { data: null, error: null };

  if (updatedByTrackerId.error) {
    return NextResponse.json(
      { error: updatedByTrackerId.error.message },
      { status: 500 }
    );
  }

  if ((updatedByTrackerId.data ?? []).length > 0) {
    return NextResponse.json({
      received: true,
      updated: updatedByTrackerId.data?.length ?? 0,
    });
  }

  if (!tracker.tracking_code) {
    return NextResponse.json({ received: true, updated: 0 });
  }

  const updatedByTrackingCode = await supabase
    .from("inbound_shipments")
    .update({
      ...payload,
      easypost_tracker_id: tracker.id ?? null,
    })
    .eq("tracking_number", tracker.tracking_code)
    .select("inbound_shipment_id");

  if (updatedByTrackingCode.error) {
    return NextResponse.json(
      { error: updatedByTrackingCode.error.message },
      { status: 500 }
    );
  }

  return NextResponse.json({
    received: true,
    updated: updatedByTrackingCode.data?.length ?? 0,
  });
}

function validateEasyPostSignature(request: Request, rawBody: string) {
  const timestamp = request.headers.get("x-timestamp");
  const path = request.headers.get("x-path");
  const signature = request.headers.get("x-hmac-signature-v2");

  if (!timestamp || !path || !signature) {
    return "Missing EasyPost HMAC headers";
  }

  const parsedTimestamp = Date.parse(timestamp);

  if (Number.isNaN(parsedTimestamp)) {
    return "Invalid EasyPost timestamp";
  }

  const ageMs = Math.abs(Date.now() - parsedTimestamp);
  const toleranceMs = timestampToleranceMinutes * 60 * 1000;

  if (ageMs > toleranceMs) {
    return "EasyPost timestamp is outside tolerance";
  }

  const signatureValue = signature.replace(/^hmac-sha256-hex=/i, "");
  const stringToSign = `${timestamp}${request.method.toUpperCase()}${path}${rawBody}`;
  const expected = crypto
    .createHmac("sha256", webhookSecret!)
    .update(stringToSign, "utf8")
    .digest("hex");

  const expectedBuffer = Buffer.from(expected, "hex");
  const actualBuffer = Buffer.from(signatureValue, "hex");

  if (
    expectedBuffer.length !== actualBuffer.length ||
    !crypto.timingSafeEqual(expectedBuffer, actualBuffer)
  ) {
    return "Invalid EasyPost signature";
  }

  return null;
}

function buildShipmentUpdatePayload(tracker: EasyPostTracker) {
  if (!tracker.tracking_code && !tracker.id) return null;

  const latestEvent = getLatestTrackingEvent(tracker);
  const deliveredDate = getDeliveredDate(tracker);
  const normalizedStatus = normalizeStatus(tracker.status);

  const payload: Record<string, unknown> = {
    carrier: tracker.carrier ?? null,
    carrier_status: tracker.status ?? null,
    normalized_status: normalizedStatus,
    shipment_status: tracker.status ?? null,
    tracking_events_json: tracker.tracking_details ?? null,
    tracking_url: tracker.public_url ?? null,
    last_tracking_sync: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  if (tracker.est_delivery_date) {
    payload.estimated_delivery_date = tracker.est_delivery_date;
  }

  if (deliveredDate) {
    payload.delivered_date = deliveredDate;
  }

  if (latestEvent) {
    payload.last_checkpoint_time = latestEvent.datetime ?? null;
    payload.last_checkpoint_location = latestEvent.tracking_location
      ? JSON.stringify(latestEvent.tracking_location)
      : null;

    if (latestEvent.status === "failure" || latestEvent.status === "error") {
      payload.exception_description = latestEvent.message ?? null;
    }
  }

  return payload;
}

function getLatestTrackingEvent(tracker: EasyPostTracker) {
  const events = tracker.tracking_details ?? [];

  return events
    .filter((event) => event.datetime)
    .sort((left, right) =>
      String(right.datetime).localeCompare(String(left.datetime))
    )[0];
}

function getDeliveredDate(tracker: EasyPostTracker) {
  const deliveredEvent = (tracker.tracking_details ?? [])
    .filter((event) => event.status === "delivered" && event.datetime)
    .sort((left, right) =>
      String(right.datetime).localeCompare(String(left.datetime))
    )[0];

  return deliveredEvent?.datetime ?? null;
}

function normalizeStatus(status?: string | null) {
  const normalized = (status ?? "").toLowerCase();

  const mapping: Record<string, string> = {
    delivered: "delivered",
    in_transit: "in_transit",
    out_for_delivery: "out_for_delivery",
    pre_transit: "pre_transit",
    available_for_pickup: "available_for_pickup",
    return_to_sender: "return_to_sender",
    failure: "exception",
    error: "exception",
    cancelled: "cancelled",
    unknown: "unknown",
  };

  return mapping[normalized] ?? normalized;
}
