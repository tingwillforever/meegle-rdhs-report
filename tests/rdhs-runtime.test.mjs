import assert from "node:assert/strict";
import test from "node:test";

import { allowPreviewFallback } from "../lib/rdhs/runtime.ts";

test("Kubernetes mode rejects preview data fallback unless explicitly enabled", () => {
  const previousTarget = process.env.DEPLOY_TARGET;
  const previousFallback = process.env.RDHS_ALLOW_DEMO_FALLBACK;
  process.env.DEPLOY_TARGET = "k8s";
  delete process.env.RDHS_ALLOW_DEMO_FALLBACK;
  try {
    assert.equal(allowPreviewFallback(), false);
    process.env.RDHS_ALLOW_DEMO_FALLBACK = "true";
    assert.equal(allowPreviewFallback(), true);
  } finally {
    if (previousTarget === undefined) delete process.env.DEPLOY_TARGET;
    else process.env.DEPLOY_TARGET = previousTarget;
    if (previousFallback === undefined) delete process.env.RDHS_ALLOW_DEMO_FALLBACK;
    else process.env.RDHS_ALLOW_DEMO_FALLBACK = previousFallback;
  }
});
