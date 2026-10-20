import fs from "node:fs";
import path from "node:path";

async function exportStaticSite() {
  const root = process.cwd();
  const staticDir = path.join(root, "dist", "static");
  const clientDir = path.join(root, "dist", "client");

  fs.mkdirSync(staticDir, { recursive: true });

  // 1. Copy client assets to staticDir
  if (fs.existsSync(clientDir)) {
    fs.cpSync(clientDir, staticDir, { recursive: true });
  }

  // 2. Render index.html via server bundle
  const basePath = process.env.RDHS_BASE_PATH || "";
  const serverEntry = path.join(root, "dist", "server", "index.js");
  const { default: worker } = await import(serverEntry);

  const res = await worker.fetch(
    new Request(`http://localhost${basePath}/`),
    {
      ASSETS: { fetch: async () => new Response("404", { status: 404 }) },
      DB: null,
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );

  if (res.status !== 200) {
    throw new Error(`Failed to prerender static index.html: HTTP ${res.status}`);
  }

  let html = await res.text();
  if (basePath) {
    html = html.replaceAll('href="/favicon.png"', `href="${basePath}/favicon.png"`);
    html = html.replaceAll('content="http://localhost:3000/og.png"', `content="https://tingwillforever.github.io${basePath}/og.png"`);
  }
  fs.writeFileSync(path.join(staticDir, "index.html"), html, "utf-8");
  // 404.html for GitHub Pages SPA client routing fallback
  fs.writeFileSync(path.join(staticDir, "404.html"), html, "utf-8");

  // 3. Add .nojekyll so GitHub Pages does not ignore _next directory
  fs.writeFileSync(path.join(staticDir, ".nojekyll"), "", "utf-8");

  // 4. Ensure reports directory exists
  const reportsSrc = path.join(root, "public", "reports");
  const reportsDst = path.join(staticDir, "reports");
  if (fs.existsSync(reportsSrc)) {
    fs.cpSync(reportsSrc, reportsDst, { recursive: true });
  }

  // 5. Ensure _next exists at both root and nested base path for GitHub Pages routing
  if (basePath) {
    const cleanBase = basePath.replace(/^\/+/, "");
    const nestedNext = path.join(staticDir, cleanBase, "_next");
    const rootNext = path.join(staticDir, "_next");
    if (fs.existsSync(nestedNext) && !fs.existsSync(rootNext)) {
      fs.cpSync(nestedNext, rootNext, { recursive: true });
    }
  }

  console.log("Static site export completed successfully at dist/static/");
}

exportStaticSite().catch((err) => {
  console.error("Static export failed:", err);
  process.exit(1);
});
