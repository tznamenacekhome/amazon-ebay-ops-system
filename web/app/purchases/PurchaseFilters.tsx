import { Search, X } from "lucide-react";

import { OPERATIONAL_STATUS_OPTIONS } from "./utils";

type PurchaseFiltersProps = {
  searchText: string;
  asinFilter: string;
  statusFilter: string;
  onSearchTextChange: (value: string) => void;
  onAsinFilterChange: (value: string) => void;
  onStatusFilterChange: (value: string) => void;
};

export function PurchaseFilters({
  searchText,
  asinFilter,
  statusFilter,
  onSearchTextChange,
  onAsinFilterChange,
  onStatusFilterChange,
}: PurchaseFiltersProps) {
  return (
    <div className="mb-4 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[320px] flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <input
            value={searchText}
            onChange={(event) => onSearchTextChange(event.target.value)}
            className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-9 text-sm"
            placeholder="Search title, ASIN, order, tracking, carrier..."
          />
          {searchText && (
            <button
              type="button"
              onClick={() => onSearchTextChange("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              aria-label="Clear search"
              title="Clear search"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        <select
          value={asinFilter}
          onChange={(event) => onAsinFilterChange(event.target.value)}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="all">All Review States</option>
          <option value="matched">Matched ASINs</option>
          <option value="needs_review">Missing Data</option>
        </select>

        <select
          value={statusFilter}
          onChange={(event) => onStatusFilterChange(event.target.value)}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="active">All Except Listed</option>
          <option value="all">All Status</option>
          {OPERATIONAL_STATUS_OPTIONS.map((status) => (
            <option key={status.value} value={status.value}>
              {status.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
