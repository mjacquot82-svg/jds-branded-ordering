import { defineConfig } from "vite";

export default defineConfig({
  server: {
    proxy: {
      "/api": {
        target: process.env.JDS_LOCAL_BACKEND_URL || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/health": {
        target: process.env.JDS_LOCAL_BACKEND_URL || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
