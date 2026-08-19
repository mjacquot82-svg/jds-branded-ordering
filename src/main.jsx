import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import { CustomerAuthProvider } from "./auth/CustomerAuthContext.jsx";
import AppErrorBoundary from "./components/AppErrorBoundary.jsx";
import "./style.css";

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/service-worker.js", { scope: "/", updateViaCache: "none" }).catch((error) => {
    console.warn("Push notification service worker registration failed.", error?.name || "RegistrationError");
  }));
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <CustomerAuthProvider>
        <AppErrorBoundary>
          <App />
        </AppErrorBoundary>
      </CustomerAuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
