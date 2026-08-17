import type { Cadence } from "./types.ts";

function constantTimeEqual(left: string, right: string): boolean {
  const encoder = new TextEncoder();
  const leftBytes = encoder.encode(left);
  const rightBytes = encoder.encode(right);
  const length = Math.max(leftBytes.length, rightBytes.length);
  let difference = leftBytes.length ^ rightBytes.length;
  for (let index = 0; index < length; index += 1) {
    difference |= (leftBytes[index] ?? 0) ^ (rightBytes[index] ?? 0);
  }
  return difference === 0;
}

export function authorizeBearer(header: string | null, expectedToken: string): boolean {
  if (!header?.startsWith("Bearer ") || expectedToken.length === 0) return false;
  return constantTimeEqual(header.slice("Bearer ".length), expectedToken);
}

export function cadenceFromUrl(url: URL): Cadence {
  const cadence = url.searchParams.get("cadence") ?? "monthly";
  if (cadence !== "weekly" && cadence !== "monthly") {
    throw new Error("cadence must be weekly or monthly");
  }
  return cadence;
}

export function periodFromUrl(url: URL, cadence: Cadence): string | undefined {
  const period = url.searchParams.get("period") ?? undefined;
  if (period === undefined) return undefined;
  const pattern = cadence === "monthly" ? /^\d{4}-\d{2}$/ : /^\d{4}-\d{2}-\d{2}$/;
  if (!pattern.test(period)) {
    throw new Error(`period must use ${cadence === "monthly" ? "YYYY-MM" : "YYYY-MM-DD"}`);
  }
  return period;
}

