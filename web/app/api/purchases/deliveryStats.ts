import type { PurchaseDeliveryStats } from "../../purchases/types";

export async function fetchDeliveryStats(client: { rpc: (name: string) => PromiseLike<{ data: unknown; error: { message: string } | null }> }): Promise<{ delivery: PurchaseDeliveryStats | null; deliveryError: string | null; deliveryDueError: string | null }> {
  try {
    const { data, error } = await client.rpc("purchase_delivery_stats");
    if (error) throw new Error(error.message);
    const value = data as PurchaseDeliveryStats | null;
    if (!value || ![value.notDelivered, value.deliveredNotReceived].every(group => group && [group.units, group.purchaseDollars, group.unpricedUnits].every(Number.isFinite))) {
      throw new Error("Purchase delivery totals returned an invalid response.");
    }
    // Keep the established backlog totals visible if the additive ETA total fails.
    try {
      const saturday = await client.rpc("purchase_saturday_delivery_stats");
      if (saturday.error) throw new Error(saturday.error.message);
      const group = saturday.data as NonNullable<PurchaseDeliveryStats["dueBySaturday"]>;
      if (!group || !/^\d{4}-\d{2}-\d{2}$/.test(group.throughDate) ||
          ![group.units, group.purchaseDollars, group.unpricedUnits].every(Number.isFinite)) {
        throw new Error("Saturday delivery total returned an invalid response.");
      }
      return { delivery: { ...value, dueBySaturday: group }, deliveryError: null, deliveryDueError: null };
    } catch (error) {
      return { delivery: value, deliveryError: null, deliveryDueError: error instanceof Error ? error.message : "Saturday delivery total unavailable." };
    }
  } catch (error) {
    return { delivery: null, deliveryError: error instanceof Error ? error.message : "Purchase delivery totals unavailable.", deliveryDueError: null };
  }
}
