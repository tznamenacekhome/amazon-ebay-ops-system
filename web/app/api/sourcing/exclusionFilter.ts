export type ExclusionOption = { code: string; label: string; count: number };
export function filterExclusions<T extends { exclusionReason?: { code: string; label: string } | null }>(rows: T[], selected = "all") {
  const options = new Map<string, ExclusionOption>([
    ["review_threshold", { code: "review_threshold", label: "Match needs review", count: 0 }],
    ["profitability", { code: "profitability", label: "Profitability", count: 0 }],
  ]);
  for (const row of rows) {
    const code = row.exclusionReason?.code ?? "unknown";
    const option = options.get(code) ?? { code, label: row.exclusionReason?.label ?? "Unspecified exclusion", count: 0 };
    option.count++; options.set(code, option);
  }
  return {
    rows: selected === "all" ? rows : rows.filter(row => (row.exclusionReason?.code ?? "unknown") === selected),
    options: [...options.values()].sort((a,b) => a.label.localeCompare(b.label)),
  };
}
