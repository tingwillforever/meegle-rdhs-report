import type { BusinessLineMetric, GovernanceBand, ProductMetric } from "./types.ts";

export type ProductFilters = {
  businessLine: string;
  band: GovernanceBand | "全部分档";
  query: string;
  unmeasuredOnly: boolean;
};

export type ProductSort = "rdhs-asc" | "rdhs-desc" | "product-asc";

export function filterProducts<T extends Pick<ProductMetric, "businessLine" | "product" | "rdhs" | "governanceBand">>(
  products: T[],
  filters: ProductFilters,
): T[] {
  const query = filters.query.trim().toLocaleLowerCase("zh-CN");
  return products.filter((product) => {
    if (filters.businessLine !== "全部业务线" && product.businessLine !== filters.businessLine) {
      return false;
    }
    if (filters.band !== "全部分档" && product.governanceBand !== filters.band) return false;
    if (filters.unmeasuredOnly && product.rdhs !== null) return false;
    if (query && !`${product.product} ${product.businessLine}`.toLocaleLowerCase("zh-CN").includes(query)) {
      return false;
    }
    return true;
  });
}

export function sortProducts<T extends Pick<ProductMetric, "product" | "rdhs">>(
  products: T[],
  sort: ProductSort,
): T[] {
  return [...products].sort((left, right) => {
    if (sort === "product-asc") return left.product.localeCompare(right.product, "zh-CN");
    if (left.rdhs === null && right.rdhs === null) {
      return left.product.localeCompare(right.product, "zh-CN");
    }
    if (left.rdhs === null) return 1;
    if (right.rdhs === null) return -1;
    const scoreOrder = sort === "rdhs-asc" ? left.rdhs - right.rdhs : right.rdhs - left.rdhs;
    return scoreOrder || left.product.localeCompare(right.product, "zh-CN");
  });
}

export function sortBusinessLines<T extends Pick<BusinessLineMetric, "businessLine" | "productTotal">>(
  lines: T[],
): T[] {
  return [...lines].sort(
    (left, right) =>
      right.productTotal - left.productTotal ||
      left.businessLine.localeCompare(right.businessLine, "zh-CN"),
  );
}
