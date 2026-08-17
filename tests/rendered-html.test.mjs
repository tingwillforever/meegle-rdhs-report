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
  assert.match(html, /<title>RDHS 产研过程效能运营报告<\/title>/i);
  assert.match(html, /消费者BG/);
  assert.match(html, /周报/);
  assert.match(html, /月报/);
  assert.match(html, /研发中产品/);
  assert.match(html, /平均 RDHS/);
  assert.match(html, /度量覆盖率/);
  assert.match(html, /低于70分/);
  assert.match(html, /70分基线/);
  assert.match(html, /数据更新时间/);
  assert.match(html, /RDHS 总览/);
  assert.match(html, /常规跟踪/);
  assert.match(html, /产品治理明细/);
  assert.match(html, /og\.png/);
});

test("finished page does not expose starter preview metadata", async () => {
  const response = await render();
  const html = await response.text();

  assert.doesNotMatch(html, /codex-preview/);
  assert.doesNotMatch(html, /Your site is taking shape/);
  assert.doesNotMatch(html, /react-loading-skeleton/);
  assert.doesNotMatch(html, /Building your site/);
});
