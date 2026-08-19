import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { fetchCustomerSession, loginCustomer, logoutCustomer } from "../services/customerAuthApi.js";

const CustomerAuthContext = createContext(null);

export function isOrderingCustomerSession(session) {
  return session?.role === "customer";
}

export function CustomerAuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [status, setStatus] = useState("loading");
  const refreshSession = useCallback(async () => {
    try {
      const value = await fetchCustomerSession();
      setSession(value); setStatus("authenticated"); return value;
    } catch {
      setSession(null); setStatus("anonymous"); return null;
    }
  }, []);
  useEffect(() => { refreshSession(); }, [refreshSession]);
  async function login(email, password, keepSignedIn = false) {
    const value = await loginCustomer(email, password, { keepSignedIn });
    setSession(value); setStatus("authenticated"); return value;
  }
  async function logout() {
    if (session?.csrf_token) await logoutCustomer(session.csrf_token);
    setSession(null); setStatus("anonymous");
  }
  return <CustomerAuthContext.Provider value={{ login, logout, refreshSession, session, status }}>{children}</CustomerAuthContext.Provider>;
}

export function useCustomerAuth() {
  const value = useContext(CustomerAuthContext);
  if (!value) throw new Error("useCustomerAuth must be used inside CustomerAuthProvider.");
  return value;
}
