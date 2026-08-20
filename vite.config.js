import { defineConfig } from "vite";
import { localReviewProxy } from "./vite.local-review-proxy.js";

const backendTarget = process.env.JDS_LOCAL_BACKEND_URL || "http://127.0.0.1:8000";
const reviewOrigin = process.env.JDS_LOCAL_REVIEW_ORIGIN || "";

export default defineConfig({
  server: {
    proxy: {
      "/api": localReviewProxy(backendTarget, reviewOrigin),
      "/health": localReviewProxy(backendTarget, reviewOrigin),
    },
  },
});
