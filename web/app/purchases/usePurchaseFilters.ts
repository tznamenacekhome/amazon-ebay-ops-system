import { useMemo, useState } from "react";

import type { PurchaseRow } from "./types";
import {
  getEbayTitle,
  getPrimaryTitle,
  getShipmentStatus,
  isDelivered,
} from "./utils";

export function usePurchaseFilters(rows: PurchaseRow[]) {
  const [searchText, setSearchText] = useState("");
  const [asinFilter, setAsinFilter] = useState("all");
  const [deliveryFilter, setDeliveryFilter] = useState("all");

  const filteredRows = useMemo(() => {
    const search = searchText.trim().toLowerCase();

    return rows.filter((row) => {
      const primaryTitle = getPrimaryTitle(row);
      const ebayTitle = getEbayTitle(row);
      const status = getShipmentStatus(row);

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
          status,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(search);

      const matchesAsin =
        asinFilter === "all" ||
        (asinFilter === "matched" && !!row.asin) ||
        (asinFilter === "needs_review" && !row.asin);

      const matchesDelivery =
        deliveryFilter === "all" ||
        (deliveryFilter === "delivered" && isDelivered(row)) ||
        (deliveryFilter === "not_delivered" && !isDelivered(row));

      return matchesSearch && matchesAsin && matchesDelivery;
    });
  }, [rows, searchText, asinFilter, deliveryFilter]);

  return {
    searchText,
    asinFilter,
    deliveryFilter,
    filteredRows,
    setSearchText,
    setAsinFilter,
    setDeliveryFilter,
  };
}
