import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("the application image consumes the prebuilt RDHS dependency image", async () => {
  const dockerfile = await readFile(new URL("../Dockerfile", import.meta.url), "utf8");

  assert.match(
    dockerfile,
    /ARG RDHS_BASE_IMAGE=artifacts\.iflytek\.com\/cbg-docker-repo\/cbbywkf\/meegle-rdhs-report-base:node22-python3-meegle-cli-1\.1\.5/,
  );
  assert.match(dockerfile, /FROM \$\{RDHS_BASE_IMAGE\} AS builder/);
  assert.match(dockerfile, /^FROM \$\{RDHS_BASE_IMAGE\}$/m);
  assert.doesNotMatch(dockerfile, /NODE_BASE_IMAGE|RUNTIME_BASE_IMAGE/);
  assert.match(
    dockerfile,
    /COPY --from=rdhs-workspace topics\/rdhs-operations\/run_periodic_report\.py \/opt\/rdhs-workspace\/topics\/rdhs-operations\/run_periodic_report\.py/,
  );
  assert.doesNotMatch(dockerfile, /COPY --from=rdhs-workspace\s+\/\s+\/opt\/rdhs-workspace/);
  assert.match(dockerfile, /RDHS_WORKSPACE_ROOT=\/opt\/rdhs-workspace/);
  assert.doesNotMatch(dockerfile, /apt-get install/);
  assert.doesNotMatch(dockerfile, /npm install --global/);
  assert.doesNotMatch(dockerfile, /python3 -m pip install/);
  assert.match(dockerfile, /COPY package\*\.json/);
  assert.match(dockerfile, /COPY --from=builder \/app\/dist \.\/dist/);
});

test("the Web production dependency set provides the Vinext server command", async () => {
  const packageManifest = JSON.parse(
    await readFile(new URL("../package.json", import.meta.url), "utf8"),
  );

  assert.ok(packageManifest.dependencies.vinext);
});

test("the Web image builds and runs with the production Ingress base path", async () => {
  const dockerfile = await readFile(new URL("../Dockerfile", import.meta.url), "utf8");
  const nextConfig = await readFile(new URL("../next.config.ts", import.meta.url), "utf8");

  assert.match(dockerfile, /RDHS_BASE_PATH=\/meegle-rdhs-report/);
  assert.match(nextConfig, /basePath: process\.env\.RDHS_BASE_PATH/);
});
