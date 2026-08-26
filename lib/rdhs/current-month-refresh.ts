import { spawn } from "node:child_process";
import { resolve } from "node:path";

const MAX_OUTPUT_LENGTH = 8_000;
const INCOMPLETE_PRODUCT_MASTER_PREFIX = "产品主数据不完整：";
let refreshInProgress = false;

export class CurrentRefreshInProgressError extends Error {
  constructor() {
    super("已有当月刷新任务正在执行");
  }
}

function currentDate(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const value = (type: string) => parts.find((part) => part.type === type)?.value;
  return `${value("year")}-${value("month")}-${value("day")}`;
}

function refreshTimeoutSeconds(): number {
  const value = Number(process.env.RDHS_CURRENT_REFRESH_TIMEOUT_SECONDS || "600");
  if (!Number.isInteger(value) || value < 1) {
    throw new Error("RDHS_CURRENT_REFRESH_TIMEOUT_SECONDS must be a positive integer");
  }
  return value;
}

function boundedOutput(value: string): string {
  const text = value.trim();
  return text.length > MAX_OUTPUT_LENGTH ? `${text.slice(-MAX_OUTPUT_LENGTH)}…` : text;
}

function refreshFailureDetail(stderr: string, stdout: string): string {
  const output = stderr || stdout;
  const messageStart = output.lastIndexOf(INCOMPLETE_PRODUCT_MASTER_PREFIX);
  if (messageStart >= 0) return output.slice(messageStart).trim();
  return boundedOutput(output);
}

export async function refreshCurrentMonth(): Promise<{ message: string }> {
  if (refreshInProgress) throw new CurrentRefreshInProgressError();
  refreshInProgress = true;
  try {
    const timeoutSeconds = refreshTimeoutSeconds();
    const outputRoot = resolve(
      process.env.RDHS_OUTPUT_ROOT || "./runtime/local-refresh-runs",
    );
    const child = spawn(
      process.env.RDHS_PYTHON_BIN || "python3",
      [
        "scripts/sync-rdhs-snapshot.py",
        "--current-month-cache",
        "--as-of",
        currentDate(),
        "--output-root",
        outputRoot,
      ],
      {
        cwd: process.cwd(),
        env: { ...process.env, RDHS_OUTPUT_ROOT: outputRoot },
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    child.stdout.on("data", (chunk: Buffer) => { stdout += chunk.toString(); });
    child.stderr.on("data", (chunk: Buffer) => { stderr += chunk.toString(); });
    const timeout = setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
    }, timeoutSeconds * 1_000);

    const result = await new Promise<{ code: number | null; error?: Error }>((resolve) => {
      child.once("error", (error) => resolve({ code: null, error }));
      child.once("close", (code) => resolve({ code }));
    });
    clearTimeout(timeout);
    if (timedOut) throw new Error(`当月数据刷新超时（${timeoutSeconds} 秒）`);
    if (result.error) throw result.error;
    if (result.code !== 0) {
      throw new Error(`当月数据刷新失败: ${refreshFailureDetail(stderr, stdout) || "同步脚本异常退出"}`);
    }
    return { message: "已更新当月缓存" };
  } finally {
    refreshInProgress = false;
  }
}
