import type { DiagnosticComparisonRow } from "../api/sourcing/diagnosticComparison";
import type { MatchingFeedback } from "../api/sourcing/matchingFeedback";

export const reviewFieldKeys: Record<string, string> = {
  derived_base: "coreProduct", included_contents: "includedContents", release_year: "releaseYear",
  core_game_identity: "coreGame", installment_number: "installment", generation: "generation",
  theme: "theme", platform_system: "platform", edition_version: "edition", region: "region",
  package_bundle_contents: "packageType", completeness: "completeness", digital_physical: "digitalPhysical",
};
export type Correction = MatchingFeedback["corrections"][number];
export type SavedCorrection = Correction & { actionId?: string; recordedAt?: string };
export function openingCell(row: Pick<DiagnosticComparisonRow, "key" | "amazon" | "ebay" | "amazonEvidence" | "ebayEvidence">, side: "amazon" | "ebay", saved: SavedCorrection[]) {
  const correction = saved.filter(c => c.field === reviewFieldKeys[row.key] && c.side === side)
    .sort((a,b) => (b.recordedAt ?? "").localeCompare(a.recordedAt ?? "") || (b.actionId ?? "").localeCompare(a.actionId ?? ""))[0];
  const evidence = side === "amazon" ? row.amazonEvidence : row.ebayEvidence;
  return { value: correction?.value ?? (correction ? null : row[side]),
    state: correction?.state ?? String(evidence?.state ?? (row[side] ? "value" : "unknown")), correction };
}
export function incorrectMatchReason(families: string[]) {
  return families.length === 1 && families[0] === "platform" ? "wrong_platform"
    : families.length === 1 && families[0] === "edition_version" ? "wrong_edition_version" : "wrong_product";
}
