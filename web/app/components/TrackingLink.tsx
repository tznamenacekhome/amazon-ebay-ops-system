import type { ReactNode } from "react";

type TrackingLinkProps = {
  trackingNumber?: string | null;
  carrier?: string | null;
  trackingUrl?: string | null;
  children?: ReactNode;
  className?: string;
  emptyLabel?: ReactNode;
};

export function carrierTrackingUrl(
  trackingNumber?: string | null,
  carrier?: string | null,
  trackingUrl?: string | null
) {
  const number = trackingNumber?.trim();
  if (!number) return null;

  const preferredUrl = safeHttpUrl(trackingUrl);
  if (preferredUrl) return preferredUrl;

  const encoded = encodeURIComponent(number);
  const normalizedCarrier = (carrier ?? "").toLowerCase();

  if (normalizedCarrier.includes("usps") || normalizedCarrier.includes("postal")) {
    return `https://tools.usps.com/go/TrackConfirmAction?tLabels=${encoded}`;
  }
  if (normalizedCarrier.includes("ups") || /^1Z/i.test(number)) {
    return `https://www.ups.com/track?loc=en_US&tracknum=${encoded}`;
  }
  if (normalizedCarrier.includes("fedex") || normalizedCarrier.includes("federal express")) {
    return `https://www.fedex.com/fedextrack/?trknbr=${encoded}`;
  }
  if (normalizedCarrier.includes("dhl")) {
    return `https://www.dhl.com/us-en/home/tracking/tracking-parcel.html?submit=1&tracking-id=${encoded}`;
  }
  if (normalizedCarrier.includes("ontrac") || normalizedCarrier.includes("lasership")) {
    return `https://www.ontrac.com/tracking/?number=${encoded}`;
  }

  return `https://www.google.com/search?q=${encodeURIComponent(`${number} tracking`)}`;
}

export function TrackingLink({
  trackingNumber,
  carrier,
  trackingUrl,
  children,
  className = "text-blue-700 hover:underline",
  emptyLabel = "--",
}: TrackingLinkProps) {
  const href = carrierTrackingUrl(trackingNumber, carrier, trackingUrl);
  if (!href || !trackingNumber) return <>{emptyLabel}</>;

  return (
    <a
      className={className}
      href={href}
      target="_blank"
      rel="noreferrer"
      title={`Track ${trackingNumber}${carrier ? ` with ${carrier}` : ""}`}
    >
      {children ?? trackingNumber}
    </a>
  );
}

function safeHttpUrl(value?: string | null) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}
