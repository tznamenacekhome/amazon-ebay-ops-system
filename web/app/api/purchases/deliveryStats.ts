import type { PurchaseDeliveryStats } from "../../purchases/types";

export async function fetchDeliveryStats(client: { rpc: (name: string) => PromiseLike<{ data: unknown; error: { message: string } | null }> }): Promise<{ delivery: PurchaseDeliveryStats | null; deliveryError: string | null; deliveryDueError: string | null }> {
  try {
    const { data, error } = await client.rpc("purchase_delivery_stats");
    if (error) throw new Error(error.message);
    const value = data as PurchaseDeliveryStats | null;
    if (!value || ![value.notDelivered, value.deliveredNotReceived].every(group => group && [group.units, group.purchaseDollars, group.unpricedUnits].every(Number.isFinite))) {
      throw new Error("Purchase delivery totals returned an invalid response.");
    }
    // Keep the established backlog totals visible if the additive ETA totals fail.
    try {
      const daily = await client.rpc("purchase_daily_delivery_stats");
      if (daily.error) throw new Error(daily.error.message);
      const result = daily.data as { days?: PurchaseDeliveryStats["dueDays"] } | null;
      const days = result?.days;
      if (!Array.isArray(days) || days.length !== 7 || days.some(group =>
        !/^\d{4}-\d{2}-\d{2}$/.test(group.dueDate) ||
        ![group.units, group.purchaseDollars, group.unpricedUnits].every(Number.isFinite))) {
        throw new Error("Daily delivery totals returned an invalid response.");
      }
      return { delivery: { ...value, dueDays: days }, deliveryError: null, deliveryDueError: null };
    } catch (error) {
      return { delivery: value, deliveryError: null, deliveryDueError: error instanceof Error ? error.message : "Daily delivery totals unavailable." };
    }
  } catch (error) {
    return { delivery: null, deliveryError: error instanceof Error ? error.message : "Purchase delivery totals unavailable.", deliveryDueError: null };
  }
}
