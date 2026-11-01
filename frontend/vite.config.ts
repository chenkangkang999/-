import { fileURLToPath, URL } from "node:url";
import vue from "@vitejs/plugin-vue";
import { defineConfig, loadEnv } from "vite";
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backend = env.DEV_API_PROXY_TARGET || "http://127.0.0.1:8000";
  return {
    plugins: [vue()],
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: {
      host: env.DEV_HOST || "127.0.0.1",
      port: Number(env.DEV_PORT || 5173),
      proxy: {
        "/api": { target: backend, changeOrigin: true },
        "/ws": { target: backend, ws: true },
      },
    },
    build: { outDir: "dist", sourcemap: false },
  };
});
