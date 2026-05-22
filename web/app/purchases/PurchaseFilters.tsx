import { Search } from "lucide-react";

type PurchaseFiltersProps = {
  searchText: string;
  asinFilter: string;
  deliveryFilter: string;
  onSearchTextChange: (value: string) => void;
  onAsinFilterChange: (value: string) => void;
  onDeliveryFilterChange: (value: string) => void;
};

export function PurchaseFilters({
  searchText,
  asinFilter,
  deliveryFilter,
  onSearchTextChange,
  onAsinFilterChange,
  onDeliveryFilterChange,
}: PurchaseFiltersProps) {
  return (
    <div className="mb-4 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[320px] flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <input
            value={searchText}
            onChange={(event) => onSearchTextChange(event.target.value)}
            className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-3 text-sm"
            placeholder="Search title, ASIN, order, tracking, carrier..."
          />
        </div>

        <select
          value={asinFilter}
          onChange={(event) => onAsinFilterChange(event.target.value)}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="all">All ASINs</option>
          <option value="matched">Matched ASINs</option>
          <option value="needs_review">Needs Review</option>
        </select>

        <select
          value={deliveryFilter}
          onChange={(event) => onDeliveryFilterChange(event.target.value)}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="all">All Deliveries</option>
          <option value="delivered">Delivered</option>
          <option value="not_delivered">Not Delivered</option>
        </select>
      </div>
    </div>
  );
}
