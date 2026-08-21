import assert from "node:assert/strict";
import test from "node:test";

import { GET as getBaseline } from "../app/api/internal/sync/baseline/route.ts";
import { POST as acquireLease } from "../app/api/internal/sync/lock/acquire/route.ts";

test("internal baseline API rejects requests without the ingest token", async () => {
  const previousStorage = process.env.RDHS_STORAGE;
  const previousToken = process.env.RDHS_INGEST_TOKEN;
  process.env.RDHS_STORAGE = "mysql";
  process.env.RDHS_INGEST_TOKEN = "test-ingest-token";
  try {
    const response = await getBaseline(
      new Request("http://localhost/api/internal/sync/baseline?period=2026-07"),
    );
    assert.equal(response.status, 401);
  } finally {
    if (previousStorage === undefined) delete process.env.RDHS_STORAGE;
    else process.env.RDHS_STORAGE = previousStorage;
    if (previousToken === undefined) delete process.env.RDHS_INGEST_TOKEN;
    else process.env.RDHS_INGEST_TOKEN = previousToken;
  }
});

test("internal lease API validates bearer authorization before opening MySQL", async () => {
  const previousStorage = process.env.RDHS_STORAGE;
  const previousToken = process.env.RDHS_INGEST_TOKEN;
  process.env.RDHS_STORAGE = "mysql";
  process.env.RDHS_INGEST_TOKEN = "test-ingest-token";
  try {
    const response = await acquireLease(
      new Request("http://localhost/api/internal/sync/lock/acquire", {
        method: "POST",
        body: JSON.stringify({ name: "report-sync", owner: "owner-1", ttlSeconds: 1800 }),
      }),
    );
    assert.equal(response.status, 401);
  } finally {
    if (previousStorage === undefined) delete process.env.RDHS_STORAGE;
    else process.env.RDHS_STORAGE = previousStorage;
    if (previousToken === undefined) delete process.env.RDHS_INGEST_TOKEN;
    else process.env.RDHS_INGEST_TOKEN = previousToken;
  }
});
