import {
  CurrentRefreshInProgressError,
  refreshCurrentMonth,
} from "@/lib/rdhs/current-month-refresh";

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

  try {
    const result = await refreshCurrentMonth();
    return Response.json({
      status: "triggered",
      message: result.message,
      periodKey,
    });
  } catch (error) {
    if (error instanceof CurrentRefreshInProgressError) {
      return Response.json({ error: error.message }, { status: 409 });
    }
    return Response.json(
      { error: error instanceof Error ? error.message : "实时刷新服务触发失败" },
      { status: 502 },
    );
  }
}
