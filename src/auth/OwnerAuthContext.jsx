import { createContext, useCallback, useContext, useRef, useState } from "react";
import { fetchAuthorizedOrganizations, fetchOwnerSession, loginOwner, loginStaff, logoutOwner, selectAuthorizedOrganization } from "../services/ownerAuthApi.js";

const OwnerAuthContext = createContext(null);

export function OwnerAuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [status, setStatus] = useState("idle");
  const [businesses, setBusinesses] = useState([]);
  const pendingSession = useRef(null);

  const refreshSession = useCallback(async () => {
    if (pendingSession.current) return pendingSession.current;
    setStatus("loading");
    pendingSession.current = fetchOwnerSession()
      .then((nextSession) => {
        setSession(nextSession);
        setStatus("authenticated");
        fetchAuthorizedOrganizations().then(setBusinesses).catch(() => setBusinesses([]));
        return nextSession;
      })
      .catch((error) => {
        setSession(null);
        setStatus("anonymous");
        throw error;
      })
      .finally(() => {
        pendingSession.current = null;
      });
    return pendingSession.current;
  }, []);

  const login = useCallback(async (email, password) => {
    const nextSession = await loginOwner(email, password);
    setSession(nextSession);
    setStatus("authenticated");
    return nextSession;
  }, []);

  const staffLogin = useCallback(async (staffId, pin) => {
    const nextSession = await loginStaff(staffId, pin);
    setSession(nextSession);
    setStatus("authenticated");
    return nextSession;
  }, []);

  const logout = useCallback(async () => {
    const csrfToken = session?.csrf_token;
    try {
      if (csrfToken) await logoutOwner(csrfToken);
    } finally {
      setSession(null);
      setStatus("anonymous");
      setBusinesses([]);
    }
  }, [session]);

  const selectBusiness = useCallback(async (membershipId) => {
    const nextSession = await selectAuthorizedOrganization(membershipId, session.csrf_token);
    setSession(nextSession);
    globalThis.location?.reload?.();
    return nextSession;
  }, [session]);

  return (
    <OwnerAuthContext.Provider value={{ businesses, login, staffLogin, logout, refreshSession, selectBusiness, session, status }}>
      {children}
    </OwnerAuthContext.Provider>
  );
}

export function useOwnerAuth() {
  const value = useContext(OwnerAuthContext);
  if (!value) throw new Error("useOwnerAuth must be used inside OwnerAuthProvider.");
  return value;
}
