import { createContext, useCallback, useContext, useRef, useState } from "react";
import { fetchOwnerSession, loginOwner, loginStaff, logoutOwner } from "../services/ownerAuthApi.js";

const OwnerAuthContext = createContext(null);

export function OwnerAuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [status, setStatus] = useState("idle");
  const pendingSession = useRef(null);

  const refreshSession = useCallback(async () => {
    if (pendingSession.current) return pendingSession.current;
    setStatus("loading");
    pendingSession.current = fetchOwnerSession()
      .then((nextSession) => {
        setSession(nextSession);
        setStatus("authenticated");
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
    }
  }, [session]);

  return (
    <OwnerAuthContext.Provider value={{ login, staffLogin, logout, refreshSession, session, status }}>
      {children}
    </OwnerAuthContext.Provider>
  );
}

export function useOwnerAuth() {
  const value = useContext(OwnerAuthContext);
  if (!value) throw new Error("useOwnerAuth must be used inside OwnerAuthProvider.");
  return value;
}
