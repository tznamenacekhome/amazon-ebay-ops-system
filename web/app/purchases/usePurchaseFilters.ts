import { useMemo, useState } from "react";

import type { PurchaseRow } from "./types";
import {
  getEbayTitle,
  getOperationalStatus,
  getPrimaryTitle,
  needsAsinReview,
} from "./utils";

export function usePurchaseFilters(rows: PurchaseRow[]) {
  const [searchText, setSearchText] = useState("");
  const [asinFilter, setAsinFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("active");

  const filteredRows = useMemo(() => {
    const search = searchText.trim().toLowerCase();

    return rows.filter((row) => {
      const primaryTitle = getPrimaryTitle(row);
      const ebayTitle = getEbayTitle(row);
      const status = getOperationalStatus(row);

      const matchesSearch =
        !search ||
        [
          primaryTitle,
          ebayTitle,
          row.asin,
          row.system,
          row.supplier_order_id,
          row.tracking_number,
          row.carrier,
          status.label,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(search);

      const matchesAsin =
        asinFilter === "all" ||
        (asinFilter === "matched" && !!row.asin) ||
        (asinFilter === "needs_review" && needsAsinReview(row));

      const matchesStatus =
        statusFilter === "all" ||
        (statusFilter === "active" && status.value !== "listed") ||
        statusFilter === status.value;

      return matchesSearch && matchesAsin && matchesStatus;
    });
  }, [rows, searchText, asinFilter, statusFilter]);

  return {
    searchText,
    asinFilter,
    statusFilter,
    filteredRows,
    setSearchText,
    setAsinFilter,
    setStatusFilter,
  };
}
