import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import { CustomerAuthProvider } from "./auth/CustomerAuthContext.jsx";
import AppErrorBoundary from "./components/AppErrorBoundary.jsx";
import "./style.css";
import { TenantProvider } from "./tenant/TenantContext.jsx";
import { applyOperationsBranding, isOperationsPath } from "./tenant/operationsBranding.js";

// Avoid flashing a café title/icon on owner, setup, and /build pages before React mounts.
if (isOperationsPath(location.pathname)) applyOperationsBranding(document, location.pathname);

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register(`/service-worker.js?tenant=${encodeURIComponent(location.hostname)}`, { scope: "/", updateViaCache: "none" }).catch((error) => {
    console.warn("Push notification service worker registration failed.", error?.name || "RegistrationError");
  }));
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <TenantProvider><CustomerAuthProvider><AppErrorBoundary><App /></AppErrorBoundary></CustomerAuthProvider></TenantProvider>
    </BrowserRouter>
  </React.StrictMode>
);
