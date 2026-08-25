import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import net from "node:net";
import { once } from "node:events";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

test("local development launcher starts the Web server and refresh runner", () => {
  const result = spawnSync("npm", ["run", "dev", "--", "--dry-run"], {
    cwd: new URL("..", import.meta.url),
    encoding: "utf8",
  });

  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /(npm run dev:web|Web already listening on 127\.0\.0\.1:3000; reusing it)/);
  assert.match(result.stdout, /(local-refresh-runner\.py|Refresh Runner already listening on 127\.0\.0\.1:8765; reusing it)/);
});

test("local development launcher reuses an already running refresh runner", async () => {
  const server = net.createServer();
  let ownsServer = true;
  server.listen(8765, "127.0.0.1");
  try {
    await once(server, "listening");
  } catch (error) {
    if (error?.code !== "EADDRINUSE") throw error;
    ownsServer = false;
  }

  try {
    const result = spawnSync("npm", ["run", "dev", "--", "--dry-run"], {
      cwd: new URL("..", import.meta.url),
      encoding: "utf8",
    });

    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /Refresh Runner already listening on 127\.0\.0\.1:8765; reusing it/);
    assert.doesNotMatch(result.stdout, /Refresh Runner: python3/);
  } finally {
    if (ownsServer) {
      server.close();
      await once(server, "close");
    }
  }
});

test("current-month refresh runs the sync script from the Web process", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "rdhs-web-refresh-"));
  const python = path.join(directory, "python-success");
  await writeFile(python, "#!/bin/sh\necho '{\"uploaded\":true}'\n", "utf8");
  await chmod(python, 0o755);
  const previous = {
    python: process.env.RDHS_PYTHON_BIN,
    timeout: process.env.RDHS_CURRENT_REFRESH_TIMEOUT_SECONDS,
  };
  process.env.RDHS_PYTHON_BIN = python;
  process.env.RDHS_CURRENT_REFRESH_TIMEOUT_SECONDS = "5";

  try {
    const { refreshCurrentMonth } = await import("../lib/rdhs/current-month-refresh.ts");
    assert.deepEqual(await refreshCurrentMonth(), { message: "已更新当月缓存" });
  } finally {
    if (previous.python === undefined) delete process.env.RDHS_PYTHON_BIN;
    else process.env.RDHS_PYTHON_BIN = previous.python;
    if (previous.timeout === undefined) delete process.env.RDHS_CURRENT_REFRESH_TIMEOUT_SECONDS;
    else process.env.RDHS_CURRENT_REFRESH_TIMEOUT_SECONDS = previous.timeout;
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
