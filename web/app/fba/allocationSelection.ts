type Allocation = {
    item_id: string;
    quantity: number;
    source_type?: string;
    source_status?: string | null;
};
export function eligibleAllocation(d: Allocation) { return d.source_type !== "amazon_return_recovery" || d.source_status === "Ready for Send to Amazon"; }
export function allocationSelection(details: Allocation[], quantities: Record<string, string>) {
    const eligible = details.filter(eligibleAllocation);
    const count = eligible.filter(d => Number(quantities[d.item_id] || 0) > 0).length;
    return { checked: eligible.length > 0 && count === eligible.length, indeterminate: count > 0 && count < eligible.length, disabled: !eligible.length };
}
export function toggleAsin(details: Allocation[], quantities: Record<string, string>, checked: boolean) {
    return { ...quantities, ...Object.fromEntries(details.map(d => [d.item_id, checked && eligibleAllocation(d) ? String(d.quantity) : "0"])) };
}
