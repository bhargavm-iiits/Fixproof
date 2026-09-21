import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const backend = process.env.FIXPROOF_API ?? "http://127.0.0.1:8000";

// Every API path is proxied in development so the app talks to the same origin
// it will be served from in production, where FastAPI serves the built bundle.
const apiPaths = [
  "/healthz",
  "/defects",
  "/runs",
  "/reports",
  "/graph",
  "/decisions",
  "/statuses",
  "/openapi.json",
  "/docs",
];

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      apiPaths.map((path) => [
        path,
        { target: backend, changeOrigin: true, ws: false },
      ]),
    ),
  },
  build: { outDir: "dist", sourcemap: true },
});
