import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

import { parseChangelog } from "./src/lib/release";

const webRoot = dirname(fileURLToPath(import.meta.url));
const projectRoot = join(webRoot, "..");

function readAppVersion() {
  try {
    const version = readFileSync(join(projectRoot, "VERSION"), "utf-8").trim();
    return version || "0.0.0";
  } catch {
    return "0.0.0";
  }
}

function readAppReleases() {
  try {
    return JSON.stringify(parseChangelog(readFileSync(join(projectRoot, "CHANGELOG.md"), "utf-8")));
  } catch {
    return "[]";
  }
}

const appVersion = process.env.VITE_APP_VERSION || readAppVersion();
const appReleases = process.env.VITE_APP_RELEASES || readAppReleases();

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": join(webRoot, "src"),
    },
  },
  define: {
    "import.meta.env.VITE_APP_VERSION": JSON.stringify(appVersion),
    "import.meta.env.VITE_APP_RELEASES": JSON.stringify(appReleases),
  },
});
