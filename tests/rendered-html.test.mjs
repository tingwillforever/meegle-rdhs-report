import assert from "node:assert/strict";
import test from "node:test";

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request(`http://localhost${path}`, {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
      DB: null,
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the RDHS operations overview", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>CBG RDHS运营报告<\/title>/i);
  assert.match(html, /CBG RDHS运营报告/);
  assert.match(html, /月报工作台/);
  assert.doesNotMatch(html, /周报/);
  assert.match(html, /月报/);
  assert.match(html, /研发中产品/);
  assert.match(html, /平均 RDHS/);
  assert.match(html, /度量覆盖率/);
  assert.match(html, /产品规范率/);
  assert.match(html, /待治理占比/);
  assert.match(html, /刷新当月/);
  assert.match(html, /历史快照已生成/);
  assert.match(html, /生成于/);
  assert.match(html, /RDHS 阈值标尺/);
  assert.match(html, /业务线总览/);
  assert.match(html, /规范占比/);
  assert.match(html, /规范占比趋势/);
  assert.match(html, /常规跟踪/);
  assert.match(html, /产品治理工作区/);
  assert.match(html, /有效参与人数/);
  assert.match(html, /产品列表分页/);
  assert.match(html, /每页/);
  assert.match(html, /悬停趋势点查看每月指标值/);
  assert.match(html, /排除交付定制/);
  assert.match(html, /数据质量审计/);
  assert.match(html, /og\.png/);
});

test("period query selects the requested historical snapshot", async () => {
  const response = await render("/?period=2026-07");
  const html = await response.text();

  assert.match(html, /<option value="2026-07" selected="">2026-07<\/option>/);
  assert.match(html, /历史快照已生成/);
});

test("expanded summary stays inside the RDHS report shell", async () => {
  const response = await render("/?period=2026-08");
  const html = await response.text();

  assert.match(html, /CBG RDHS运营报告/);
  assert.match(html, /重点关注业务线/);
  assert.match(html, /RDHS 分项得分/);
  assert.match(html, /当前分 \/ 满分/);
});

test("finished page does not expose starter preview metadata", async () => {
  const response = await render();
  const html = await response.text();

  assert.doesNotMatch(html, /codex-preview/);
  assert.doesNotMatch(html, /Your site is taking shape/);
  assert.doesNotMatch(html, /react-loading-skeleton/);
  assert.doesNotMatch(html, /Building your site/);
  assert.doesNotMatch(html, /总体判断扩展预览/);
});
