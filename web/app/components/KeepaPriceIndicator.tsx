"use client";

import { Crown } from "lucide-react";

export type KeepaFulfillment = "fba" | "mf" | null;

export function KeepaPriceIndicator({
  price,
  fulfillment,
  isBuyBox,
  formatMoney,
  usedOnly = false,
}: {
  price: number | null;
  fulfillment: KeepaFulfillment;
  isBuyBox: boolean;
  formatMoney: (value?: number | null) => string;
  usedOnly?: boolean;
}) {
  if (usedOnly) {
    return (
      <div className="flex items-center justify-end">
        <span className="text-xs font-semibold uppercase leading-tight text-slate-500">
          Used
          <br />
          Only
        </span>
      </div>
    );
  }

  const icon = fulfillmentIcon(fulfillment);

  return (
    <div className="flex items-center justify-end gap-1.5">
      <span className="font-medium text-slate-900">{formatMoney(price)}</span>
      <span
        className={`flex min-w-[34px] flex-col items-center gap-px ${isBuyBox || icon ? "" : "invisible"}`}
        aria-hidden={isBuyBox || icon ? undefined : "true"}
      >
        {isBuyBox ? (
          <Crown
            aria-label="Keepa-observed Buy Box"
            className="h-3.5 w-3.5 shrink-0 text-amber-500"
            strokeWidth={2.4}
          />
        ) : null}
        {icon ? (
          <img
            src={icon.src}
            alt={icon.alt}
            title={icon.alt}
            width={40}
            height={26}
            className="h-[22px] w-[34px] shrink-0"
          />
        ) : null}
      </span>
    </div>
  );
}

function fulfillmentIcon(fulfillment: KeepaFulfillment) {
  if (fulfillment === "fba") {
    return { src: "/icons/fulfillment/fba.svg", alt: "Fulfilled by Amazon" };
  }
  if (fulfillment === "mf") {
    return { src: "/icons/fulfillment/mf.svg", alt: "Merchant fulfilled" };
  }
  return null;
}
