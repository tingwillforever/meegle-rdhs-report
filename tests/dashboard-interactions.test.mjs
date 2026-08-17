import assert from "node:assert/strict";
import test from "node:test";

import {
  filterProducts,
  sortBusinessLines,
  sortProducts,
} from "../lib/rdhs/filter.ts";

const products = [
  {
    businessLine: "开放平台业务群",
    product: "开放平台控制台",
    rdhs: null,
    governanceBand: "重点治理",
  },
  {
    businessLine: "AI营销业务群",
    product: "营销云",
    rdhs: 52,
    governanceBand: "风险改进",
  },
  {
    businessLine: "AI营销业务群",
    product: "智能投放",
    rdhs: 72,
    governanceBand: "常规跟踪",
  },
];

test("product filters compose business line, band, search, and unmeasured state", () => {
  assert.deepEqual(
    filterProducts(products, {
      businessLine: "AI营销业务群",
      band: "风险改进",
      query: "营销",
      unmeasuredOnly: false,
    }).map((product) => product.product),
    ["营销云"],
  );

  assert.deepEqual(
    filterProducts(products, {
      businessLine: "全部业务线",
      band: "全部分档",
      query: "",
      unmeasuredOnly: true,
    }).map((product) => product.product),
    ["开放平台控制台"],
  );
});

test("score sorting keeps unmeasured products after measured scores", () => {
  assert.deepEqual(
    sortProducts(products, "rdhs-asc").map((product) => product.product),
    ["营销云", "智能投放", "开放平台控制台"],
  );
  assert.deepEqual(
    sortProducts(products, "rdhs-desc").map((product) => product.product),
    ["智能投放", "营销云", "开放平台控制台"],
  );
});

test("business lines sort by product volume and then stable Chinese name", () => {
  const lines = [
    { businessLine: "讯飞听见", productTotal: 14 },
    { businessLine: "AI文娱业务群", productTotal: 8 },
    { businessLine: "开放平台业务群", productTotal: 21 },
  ];

  assert.deepEqual(
    sortBusinessLines(lines).map((line) => line.businessLine),
    ["开放平台业务群", "讯飞听见", "AI文娱业务群"],
  );
});
