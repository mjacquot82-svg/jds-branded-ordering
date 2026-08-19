import { useEffect, useRef, useState } from "react";
import { LogOut } from "lucide-react";
import { Navigate, NavLink, Outlet, useLocation } from "react-router-dom";
import { useOwnerAuth } from "./OwnerAuthContext.jsx";
import { ownerLoginDestination } from "./ownerAuthRouting.js";
import { canAccessOwnerPath, operationsLinks } from "./ownerProductPermissions.js";

export default function RequireOwner() {
  const location = useLocation();
  const attempted = useRef(false);
  const [logoutDestination, setLogoutDestination] = useState(null);
  const { logout, refreshSession, session, status } = useOwnerAuth();

  async function signOut() {
    const destination = session?.role === "staff" ? "/staff" : "/owner/login";
    setLogoutDestination(destination);
    try {
      await logout();
    } catch {
      // logout() still clears local authentication state in its finally block.
    }
  }

  useEffect(() => {
    if (logoutDestination || session || status === "loading" || attempted.current) return;
    attempted.current = true;
    refreshSession().catch(() => {});
  }, [logoutDestination, refreshSession, session, status]);

  if (logoutDestination && !session && status === "anonymous") {
    return <Navigate replace to={logoutDestination} />;
  }
  if (logoutDestination) return (
    <section className="page-section compact-section" aria-live="polite">
      <div className="operations-panel">
        <h1>Signing out…</h1>
        <p>Closing your secure Operations session.</p>
      </div>
    </section>
  );
  if (session && canAccessOwnerPath(session, location.pathname)) return <>
    <nav className="admin-links operations-nav" aria-label="Operations Portal navigation">
      {operationsLinks(session).map((link) => <NavLink end={link.end} key={link.to} to={link.to}>{link.label}</NavLink>)}
      <button className="secondary-button operations-nav-signout" type="button" onClick={signOut}><LogOut size={17} /> Sign out</button>
    </nav>
    <Outlet />
  </>;
  if (session) return <Navigate replace to={operationsLinks(session)[0]?.to || "/owner/login?denied=1"} />;
  if (status === "anonymous") {
    const returnTo = ownerLoginDestination(location);
    return <Navigate replace to={`/owner/login?returnTo=${encodeURIComponent(returnTo)}`} />;
  }
  return (
    <section className="page-section compact-section" aria-live="polite">
      <div className="operations-panel">
        <h1>Owner Portal</h1>
        <p>Checking your secure owner session…</p>
      </div>
    </section>
  );
}
