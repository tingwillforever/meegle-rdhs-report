type RuntimeBindings = Record<string, unknown>;

const RUNTIME_BINDINGS_KEY = "__RDHS_RUNTIME_BINDINGS__";

function processEnv(): NodeJS.ProcessEnv | undefined {
  return typeof process === "undefined" ? undefined : process.env;
}

export function isSQLiteStorage(): boolean {
  const env = processEnv();
  return env?.RDHS_STORAGE === "sqlite" || env?.DEPLOY_TARGET === "k8s";
}

export function allowPreviewFallback(): boolean {
  return processEnv()?.DEPLOY_TARGET !== "k8s" || processEnv()?.RDHS_ALLOW_DEMO_FALLBACK === "true";
}

export function setRuntimeBindings(bindings: RuntimeBindings): void {
  (globalThis as typeof globalThis & { [RUNTIME_BINDINGS_KEY]?: RuntimeBindings })[
    RUNTIME_BINDINGS_KEY
  ] = bindings;
}

export function getRuntimeBinding(name: string): unknown {
  if (isSQLiteStorage()) return processEnv()?.[name];
  return (
    globalThis as typeof globalThis & { [RUNTIME_BINDINGS_KEY]?: RuntimeBindings }
  )[RUNTIME_BINDINGS_KEY]?.[name];
}

export function getRuntimeSetting(name: string): string {
  return String(getRuntimeBinding(name) ?? "");
}
