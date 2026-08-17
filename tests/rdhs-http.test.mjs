import assert from "node:assert/strict";
import test from "node:test";

import {
  authorizeBearer,
  cadenceFromUrl,
  periodFromUrl,
} from "../lib/rdhs/http.ts";

test("ingest authorization accepts only the exact bearer token", () => {
  assert.equal(authorizeBearer("Bearer sync-secret", "sync-secret"), true);
  assert.equal(authorizeBearer("Bearer sync-secret-x", "sync-secret"), false);
  assert.equal(authorizeBearer("Basic sync-secret", "sync-secret"), false);
  assert.equal(authorizeBearer(null, "sync-secret"), false);
  assert.equal(authorizeBearer("Bearer sync-secret", ""), false);
});

test("cadence query defaults to monthly and rejects unknown values", () => {
  assert.equal(cadenceFromUrl(new URL("https://example.com/api/report")), "monthly");
  assert.equal(
    cadenceFromUrl(new URL("https://example.com/api/report?cadence=weekly")),
    "weekly",
  );
  assert.throws(
    () => cadenceFromUrl(new URL("https://example.com/api/report?cadence=daily")),
    /cadence must be weekly or monthly/,
  );
});

test("period query validates against the selected cadence", () => {
  assert.equal(
    periodFromUrl(new URL("https://example.com/api/report?period=2026-08"), "monthly"),
    "2026-08",
  );
  assert.equal(periodFromUrl(new URL("https://example.com/api/report"), "monthly"), undefined);
  assert.throws(
    () => periodFromUrl(new URL("https://example.com/api/report?period=2026-08"), "weekly"),
    /period must use YYYY-MM-DD/,
  );
});

