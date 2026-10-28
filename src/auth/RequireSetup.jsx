import { useEffect, useRef } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useOwnerAuth } from "./OwnerAuthContext.jsx";
import { ownerLoginDestination } from "./ownerAuthRouting.js";

export default function RequireSetup() {
  const location = useLocation();
  const attempted = useRef(false);
  const { refreshSession, session, status } = useOwnerAuth();

  useEffect(() => {
    if (session || status === "loading" || attempted.current) return;
    attempted.current = true;
    refreshSession().catch(() => {});
  }, [refreshSession, session, status]);

  if (session?.app_launched) return <Navigate replace to="/admin" />;
  if (session && ["owner", "manager"].includes(session.role)) return <Outlet />;
  if (session) return <Navigate replace to="/admin" />;
  if (status === "anonymous") {
    return <Navigate replace to={`/owner/login?returnTo=${encodeURIComponent(ownerLoginDestination(location))}`} />;
  }
  return <main className="setup-auth-loading" aria-live="polite"><strong>Preparing your setup…</strong></main>;
}
