import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { execSync } from "child_process";

// Get build info at build time
function getBuildInfo() {
  let gitCommit = "dev";
  let gitBranch = "local";
  try {
    gitCommit = execSync("git rev-parse --short HEAD", { encoding: "utf-8" }).trim();
    gitBranch = execSync("git rev-parse --abbrev-ref HEAD", { encoding: "utf-8" }).trim();
  } catch {
    // Not in a git repo or git not available
  }
  return {
    commit: gitCommit,
    branch: gitBranch,
    buildTime: new Date().toISOString(),
  };
}

const buildInfo = getBuildInfo();

// https://vitejs.dev/config/
export default defineConfig(() => ({
  server: {
    host: "::",
    port: 8080,
    hmr: {
      overlay: false,
    },
    proxy: {
      "/api/v1": { target: "http://localhost:5000", changeOrigin: true },
      "/health": { target: "http://localhost:5000", changeOrigin: true },
    },
  },
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  define: {
    __BUILD_COMMIT__: JSON.stringify(buildInfo.commit),
    __BUILD_BRANCH__: JSON.stringify(buildInfo.branch),
    __BUILD_TIME__: JSON.stringify(buildInfo.buildTime),
  },
}));
