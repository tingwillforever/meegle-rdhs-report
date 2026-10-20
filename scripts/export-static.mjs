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
  const basePath = process.env.RDHS_BASE_PATH ? process.env.RDHS_BASE_PATH.replace(/\/+$/, "") : "";
  const requestPath = basePath ? basePath : "/";
  const serverEntry = path.join(root, "dist", "server", "index.js");
  const { default: worker } = await import(serverEntry);

  const res = await worker.fetch(
    new Request(`http://localhost${requestPath}`),
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
  // Cached vinext font CSS may retain filesystem URLs from an earlier checkout.
  html = html.replace(/(?:[A-Za-z]:)?\/[^\s"'()<>]*\/\.vinext\/fonts\//g, `${basePath}/_next/static/_vinext_fonts/`);
  if (basePath) {
    html = html.replaceAll('href="/favicon.png"', `href="${basePath}/favicon.png"`);
    html = html.replaceAll('content="http://localhost:3000/og.png"', `content="https://tingwillforever.github.io${basePath}/og.png"`);
    html = html.replaceAll('href="/_next/', `href="${basePath}/_next/`);
    html = html.replaceAll('src="/_next/', `src="${basePath}/_next/`);
    html = html.replaceAll('url(/_next/', `url(${basePath}/_next/`);
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

  // 5. Ensure _next and html exist at both root and nested base path for GitHub Pages routing
  if (basePath) {
    const cleanBase = basePath.replace(/^\/+/, "");
    const baseDir = path.join(staticDir, cleanBase);
    fs.mkdirSync(baseDir, { recursive: true });
    fs.writeFileSync(path.join(baseDir, "index.html"), html, "utf-8");
    fs.writeFileSync(path.join(baseDir, "404.html"), html, "utf-8");

    const rootNext = path.join(staticDir, "_next");
    const nestedNext = path.join(baseDir, "_next");
    // Pages strips the repository prefix before looking up artifact files.
    if (fs.existsSync(nestedNext) && !fs.existsSync(rootNext)) {
      fs.cpSync(nestedNext, rootNext, { recursive: true });
    }
    if (fs.existsSync(rootNext) && !fs.existsSync(nestedNext)) {
      fs.cpSync(rootNext, nestedNext, { recursive: true });
    }
  }

  console.log("Static site export completed successfully at dist/static/");
}

exportStaticSite().catch((err) => {
  console.error("Static export failed:", err);
  process.exit(1);
});
