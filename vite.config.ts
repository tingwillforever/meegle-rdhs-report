import vinext from "vinext";
import { defineConfig, type PluginOption } from "vite";

const SITE_CREATOR_PLACEHOLDER_DATABASE_ID =
  "00000000-0000-4000-8000-000000000000";

// macOS Seatbelt blocks FSEvents, so Codex previews need polling for HMR.
const isCodexSeatbeltSandbox = process.env.CODEX_SANDBOX === "seatbelt";
const isKubernetesTarget = process.env.DEPLOY_TARGET === "k8s";

export default defineConfig(async () => {
  // Keep Wrangler and Miniflare state project-local. These are non-secret tool
  // settings; application environment belongs in ignored `.env*` files.
  process.env.WRANGLER_WRITE_LOGS ??= "false";
  process.env.WRANGLER_LOG_PATH ??= ".wrangler/logs";
  process.env.MINIFLARE_REGISTRY_PATH ??= ".wrangler/registry";

  const plugins: PluginOption[] = [vinext()];

  if (!isKubernetesTarget) {
    // Keep Cloudflare/Sites dependencies out of the K8s Node build path.
    const [{ sites }, { cloudflare }, hostingModule] = await Promise.all([
      import("@openai/sites-vite-plugin"),
      import("@cloudflare/vite-plugin"),
      import("./.openai/hosting.json"),
    ]);
    const { d1, r2 } = hostingModule.default;
    const localBindingConfig = {
      main: "./worker/index.ts",
      compatibility_flags: ["nodejs_compat"],
      d1_databases: d1
        ? [
            {
              binding: d1,
              database_name: "site-creator-d1",
              database_id: SITE_CREATOR_PLACEHOLDER_DATABASE_ID,
            },
          ]
        : [],
      r2_buckets: r2
        ? [
            {
              binding: r2,
              bucket_name: "site-creator-r2",
            },
          ]
        : [],
    };
    plugins.push(
      sites(),
      cloudflare({
        viteEnvironment: { name: "rsc", childEnvironments: ["ssr"] },
        config: localBindingConfig,
      }),
    );
  }

  return {
    ssr: {
      external: ["mysql2"],
    },
    server: isCodexSeatbeltSandbox
      ? { watch: { useFsEvents: false, usePolling: true } }
      : undefined,
    plugins,
  };
});
