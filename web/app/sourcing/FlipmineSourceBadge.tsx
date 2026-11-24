export function FlipmineSourceBadge({ sources }: { sources?: string[] }) {
  return sources?.includes('flipmine') ? <span title="Discovered through Flipmine; evaluated by MBOP" className="ml-2 inline-block rounded bg-sky-100 px-1 text-[10px] font-semibold text-sky-800">FM</span> : null;
}
