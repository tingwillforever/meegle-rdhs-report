import { env } from "cloudflare:workers";

export const dynamic = "force-dynamic";

type RefreshPayload = {
  periodKey: string;
};

function currentMonthKey() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
  }).formatToParts(new Date());
  const year = parts.find((part) => part.type === "year")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  return `${year}-${month}`;
}

export async function POST(request: Request) {
  let payload: Partial<RefreshPayload> = {};
  try {
    payload = (await request.json()) as Partial<RefreshPayload>;
  } catch {
    // An empty body still means "refresh the current month".
  }

  const periodKey = payload.periodKey ?? currentMonthKey();
  if (!/^\d{4}-\d{2}$/.test(periodKey)) {
    return Response.json({ error: "periodKey must use YYYY-MM" }, { status: 400 });
  }

  if (periodKey !== currentMonthKey()) {
    return Response.json(
      { error: "历史月份使用月初固化快照，不支持实时刷新" },
      { status: 409 },
    );
  }

  const refreshUrl = String(env.RDHS_REFRESH_WEBHOOK_URL ?? "");
  if (!refreshUrl) {
    return Response.json(
      {
        error: "当前部署未配置实时刷新服务，页面继续展示当月缓存数据",
        mode: "cache",
      },
      { status: 501 },
    );
  }

  const headers: HeadersInit = {
    "Content-Type": "application/json; charset=utf-8",
  };
  const token = String(env.RDHS_REFRESH_WEBHOOK_TOKEN ?? "");
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(refreshUrl, {
    method: "POST",
    headers,
    body: JSON.stringify({
      cadence: "monthly",
      periodKey,
      mode: "current-month-cache-refresh",
    }),
  });
  const detail = await response.text();
  if (!response.ok) {
    return Response.json(
      { error: detail || "实时刷新服务触发失败" },
      { status: 502 },
    );
  }
  let runnerPayload: { message?: unknown } = {};
  try {
    const parsed = JSON.parse(detail) as unknown;
    runnerPayload = typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    // Plain-text runners are also accepted; the standard message below remains enough.
  }

  return Response.json({
    status: "triggered",
    message:
      typeof runnerPayload.message === "string"
        ? runnerPayload.message
        : "已触发当月实时刷新，完成后将覆盖当月缓存",
    periodKey,
  });
}
