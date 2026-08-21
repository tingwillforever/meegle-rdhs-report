import { getRuntimeBinding } from "@/lib/rdhs/runtime";

export type D1Statement = {
  bind(...values: unknown[]): D1Statement;
  first<T = unknown>(): Promise<T | undefined>;
  all<T = unknown>(): Promise<{ results: T[] }>;
  run(): Promise<unknown>;
};

export type D1DatabaseLike = {
  prepare(query: string): D1Statement;
  batch(statements: D1Statement[]): Promise<unknown>;
};

export function getD1(): D1DatabaseLike {
  const database = getRuntimeBinding("DB") as D1DatabaseLike | undefined;
  if (!database) {
    throw new Error(
      "Cloudflare D1 binding `DB` is unavailable. Configure the logical DB binding before using RDHS persistence."
    );
  }
  return database;
}
