import assert from "node:assert/strict";
import test from "node:test";

import { GET } from "../app/api/health/route.ts";
import { GET as live } from "../app/api/health/live/route.ts";

test("health endpoint reports SQLite readiness in Kubernetes mode", async () => {
  const previousStorage = process.env.RDHS_STORAGE;
  const previousPath = process.env.RDHS_DB_PATH;
  process.env.RDHS_STORAGE = "sqlite";
  process.env.RDHS_DB_PATH = ":memory:";
  try {
    const response = await GET();
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { status: "ok", storage: "sqlite" });
  } finally {
    if (previousStorage === undefined) delete process.env.RDHS_STORAGE;
    else process.env.RDHS_STORAGE = previousStorage;
    if (previousPath === undefined) delete process.env.RDHS_DB_PATH;
    else process.env.RDHS_DB_PATH = previousPath;
  }
});

test("liveness endpoint does not depend on SQLite availability", async () => {
  const response = await live();
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { status: "ok" });
});
