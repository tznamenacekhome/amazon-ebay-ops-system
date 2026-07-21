export type TrackingScanNormalization = {
  raw: string;
  normalizedInput: string;
  candidates: string[];
};

const USPS_PREFIXES = ["94", "92", "93", "95", "96", "91", "70"];
const USPS_LENGTHS = [20, 22, 26, 30];
const FEDEX_LENGTHS = [12, 15, 20, 22];
const GENERIC_NUMERIC_LENGTHS = [10, 11, 12, 14, 20, 22];
const UPS_TRACKING_LENGTH = 18;

export function normalizeTrackingScan(
  input?: string | null
): TrackingScanNormalization {
  const raw = String(input ?? "").trim();
  const normalizedInput = cleanTrackingScanValue(raw);

  if (!normalizedInput) {
    return { raw, normalizedInput, candidates: [] };
  }

  const candidates: string[] = [];
  const upperInput = normalizedInput.toUpperCase();
  const isNumeric = /^\d+$/.test(normalizedInput);

  addCandidate(candidates, normalizedInput);
  addCandidate(candidates, upperInput);

  if (isNumeric) {
    addUspsPostalRoutingCandidates(candidates, normalizedInput);
    addUspsSuffixCandidates(candidates, normalizedInput);
    addTrailingNumericCandidates(candidates, normalizedInput, FEDEX_LENGTHS);
    addTrailingNumericCandidates(candidates, normalizedInput, GENERIC_NUMERIC_LENGTHS);
  }

  addUpsCandidates(candidates, upperInput);

  return { raw, normalizedInput, candidates };
}

export function isLikelyTrackingScan(input?: string | null) {
  const raw = String(input ?? "").trim();
  const normalizedInput = cleanTrackingScanValue(raw);
  if (!normalizedInput) return false;
  if (/^\d{2}-\d{5}-\d{5}$/.test(raw)) return false;

  const upperInput = normalizedInput.toUpperCase();
  if (upperInput.includes("1Z")) return true;
  if (!/^\d+$/.test(normalizedInput)) return false;

  return normalizedInput.length >= 12;
}

export function cleanTrackingScanValue(input?: string | null) {
  return String(input ?? "")
    .trim()
    .replace(/[^0-9A-Za-z]+/g, "");
}

function addUspsPostalRoutingCandidates(candidates: string[], value: string) {
  if (!value.startsWith("420")) return;

  if (value.length > 8) {
    addCandidate(candidates, value.slice(8));
  }

  if (value.length > 12) {
    addCandidate(candidates, value.slice(12));
  }
}

function addUspsSuffixCandidates(candidates: string[], value: string) {
  for (const length of USPS_LENGTHS) {
    if (value.length < length) continue;

    const suffix = value.slice(-length);
    if (USPS_PREFIXES.some((prefix) => suffix.startsWith(prefix))) {
      addCandidate(candidates, suffix);
    }
  }
}

function addUpsCandidates(candidates: string[], value: string) {
  const startIndex = value.indexOf("1Z");
  if (startIndex === -1) return;

  const from1z = value.slice(startIndex);
  addCandidate(candidates, from1z);

  if (from1z.length >= UPS_TRACKING_LENGTH) {
    addCandidate(candidates, from1z.slice(0, UPS_TRACKING_LENGTH));
  }
}

function addTrailingNumericCandidates(
  candidates: string[],
  value: string,
  lengths: number[]
) {
  for (const length of lengths) {
    if (value.length >= length) {
      addCandidate(candidates, value.slice(-length));
    }
  }
}

function addCandidate(candidates: string[], value: string) {
  if (!value || candidates.includes(value)) return;

  candidates.push(value);
}
