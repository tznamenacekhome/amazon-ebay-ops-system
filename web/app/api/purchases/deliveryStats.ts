import type { PurchaseDeliveryStats } from "../../purchases/types";

export async function fetchDeliveryStats(client: { rpc: (name: string) => PromiseLike<{ data: unknown; error: { message: string } | null }> }): Promise<{ delivery: PurchaseDeliveryStats | null; deliveryError: string | null }> {
  try {
    const { data, error } = await client.rpc("purchase_delivery_stats");
    if (error) throw new Error(error.message);
    const value = data as PurchaseDeliveryStats | null;
    if (!value || ![value.notDelivered, value.deliveredNotReceived].every(group => group && [group.units, group.purchaseDollars, group.unpricedUnits].every(Number.isFinite))) {
      throw new Error("Purchase delivery totals returned an invalid response.");
    }
    return { delivery: value, deliveryError: null };
  } catch (error) {
    return { delivery: null, deliveryError: error instanceof Error ? error.message : "Purchase delivery totals unavailable." };
  }
}
