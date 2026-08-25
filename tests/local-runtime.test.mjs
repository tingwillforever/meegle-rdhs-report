import assert from "node:assert/strict";
import { access, chmod, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

test("local development has no separate refresh process", async () => {
  const packageJson = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));

  await assert.rejects(() => access(new URL("../scripts/dev-local.mjs", import.meta.url)));
  await assert.rejects(() => access(new URL("../scripts/local-refresh-runner.py", import.meta.url)));
  assert.doesNotMatch(packageJson.scripts.dev, /dev-local|refresh-runner/);
  assert.equal(packageJson.scripts["dev:refresh-runner"], undefined);
});

test("default local development uses the Node runtime and loads .dev.vars", async () => {
  const packageJson = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));

  assert.match(packageJson.scripts.dev, /DEPLOY_TARGET=k8s/);
  assert.match(packageJson.scripts.dev, /node --env-file=\.dev\.vars/);
  assert.match(packageJson.scripts.dev, /node_modules\/vinext\/dist\/cli\.js dev/);
});

test("current-month refresh runs the sync script from the Web process", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "rdhs-web-refresh-"));
  const python = path.join(directory, "python-success");
  const outputRoot = path.join(process.cwd(), "runtime", "local-refresh-runs");
  await writeFile(
    python,
    `#!/bin/sh\ntest "$RDHS_OUTPUT_ROOT" = "${outputRoot}" || exit 1\necho '{"uploaded":true}'\n`,
    "utf8",
  );
  await chmod(python, 0o755);
  const previous = {
    python: process.env.RDHS_PYTHON_BIN,
    timeout: process.env.RDHS_CURRENT_REFRESH_TIMEOUT_SECONDS,
    outputRoot: process.env.RDHS_OUTPUT_ROOT,
  };
  process.env.RDHS_PYTHON_BIN = python;
  process.env.RDHS_CURRENT_REFRESH_TIMEOUT_SECONDS = "5";
  delete process.env.RDHS_OUTPUT_ROOT;

  try {
    const { refreshCurrentMonth } = await import("../lib/rdhs/current-month-refresh.ts");
    assert.deepEqual(await refreshCurrentMonth(), { message: "已更新当月缓存" });
  } finally {
    if (previous.python === undefined) delete process.env.RDHS_PYTHON_BIN;
    else process.env.RDHS_PYTHON_BIN = previous.python;
    if (previous.timeout === undefined) delete process.env.RDHS_CURRENT_REFRESH_TIMEOUT_SECONDS;
    else process.env.RDHS_CURRENT_REFRESH_TIMEOUT_SECONDS = previous.timeout;
    if (previous.outputRoot === undefined) delete process.env.RDHS_OUTPUT_ROOT;
    else process.env.RDHS_OUTPUT_ROOT = previous.outputRoot;
    await rm(directory, { recursive: true, force: true });
  }
});

test("current-month refresh rejects a second request while the first is running", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "rdhs-web-refresh-"));
  const python = path.join(directory, "python-slow-success");
  await writeFile(python, "#!/bin/sh\nsleep 0.2\necho '{\"uploaded\":true}'\n", "utf8");
  await chmod(python, 0o755);
  const previous = process.env.RDHS_PYTHON_BIN;
  process.env.RDHS_PYTHON_BIN = python;

  try {
    const { CurrentRefreshInProgressError, refreshCurrentMonth } = await import("../lib/rdhs/current-month-refresh.ts");
    const first = refreshCurrentMonth();
    await assert.rejects(() => refreshCurrentMonth(), CurrentRefreshInProgressError);
    await first;
  } finally {
    if (previous === undefined) delete process.env.RDHS_PYTHON_BIN;
    else process.env.RDHS_PYTHON_BIN = previous;
    await rm(directory, { recursive: true, force: true });
  }
});
