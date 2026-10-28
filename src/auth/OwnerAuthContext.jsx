import { createContext, useCallback, useContext, useRef, useState } from "react";
import { completeMerchantActivation, fetchAuthorizedOrganizations, fetchOwnerSession, loginOwner, loginStaff, logoutOwner, selectAuthorizedOrganization } from "../services/ownerAuthApi.js";
import { fetchPlatformCapabilities } from "../services/designStudioApi.js";
import { ownerEntryPath } from "./ownerAuthRouting.js";

const OwnerAuthContext = createContext(null);

export function OwnerAuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [status, setStatus] = useState("idle");
  const [businesses, setBusinesses] = useState([]);
  const [businessStatus,setBusinessStatus]=useState("idle");const [businessError,setBusinessError]=useState("");
  const pendingSession = useRef(null);
  const loadBusinesses=useCallback(async()=>{setBusinessStatus("loading");setBusinessError("");try{const items=await fetchAuthorizedOrganizations();setBusinesses(items);setBusinessStatus("ready");return items;}catch(error){setBusinesses([]);setBusinessStatus("error");setBusinessError(error.message);throw error;}},[]);

  // Platform capabilities load after the session; routes such as /admin/platform wait for
  // platform_capabilities_loaded instead of bouncing a deep link to the first operations page.
  const loadPlatformCapabilities = useCallback(() => {
    fetchPlatformCapabilities()
      .then(({ capabilities }) => setSession((current) => current ? ({ ...current, platform_capabilities: capabilities, platform_capabilities_loaded: true }) : current))
      .catch(() => setSession((current) => current ? ({ ...current, platform_capabilities_loaded: true }) : current));
  }, []);

  const refreshSession = useCallback(async () => {
    if (pendingSession.current) return pendingSession.current;
    setStatus("loading");
    pendingSession.current = fetchOwnerSession()
      .then((nextSession) => {
        setSession({ ...nextSession, platform_capabilities: [], platform_capabilities_loaded: false });
        setStatus("authenticated");
        loadBusinesses().catch(() => {});
        loadPlatformCapabilities();
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
  }, [loadBusinesses, loadPlatformCapabilities]);

  const login = useCallback(async (email, password) => {
    const nextSession = await loginOwner(email, password);
    setSession({ ...nextSession, platform_capabilities: [], platform_capabilities_loaded: false });
    setStatus("authenticated");
    loadBusinesses().catch(() => {});
    loadPlatformCapabilities();
    return nextSession;
  }, [loadBusinesses, loadPlatformCapabilities]);

  const staffLogin = useCallback(async (staffId, pin) => {
    const nextSession = await loginStaff(staffId, pin);
    setSession({ ...nextSession, platform_capabilities: [] });
    setStatus("authenticated");
    return nextSession;
  }, []);

  const activate = useCallback(async (activationSecret, email, password) => {
    const nextSession = await completeMerchantActivation(activationSecret, email, password);
    setSession({ ...nextSession, platform_capabilities: [] });
    setStatus("authenticated");
    await loadBusinesses();
    return nextSession;
  }, [loadBusinesses]);

  const logout = useCallback(async () => {
    const csrfToken = session?.csrf_token;
    try {
      if (csrfToken) await logoutOwner(csrfToken);
    } finally {
      setSession(null);
      setStatus("anonymous");
      setBusinesses([]);
      setBusinessStatus("idle");setBusinessError("");
    }
  }, [session]);

  const selectBusiness = useCallback(async (membershipId) => {
    setBusinessStatus("switching");setBusinessError("");
    try{const nextSession = await selectAuthorizedOrganization(membershipId, session.csrf_token);
      setSession({ ...nextSession, platform_capabilities: session.platform_capabilities || [] });
      globalThis.location?.assign?.(ownerEntryPath(nextSession));return nextSession;
    }catch(error){setBusinessStatus("error");setBusinessError(error.message);await loadBusinesses().catch(()=>{});throw error;}
  }, [loadBusinesses,session]);

  return (
    <OwnerAuthContext.Provider value={{ activate, businesses, businessError, businessStatus, login, staffLogin, logout, refreshSession, selectBusiness, session, status }}>
      {children}
    </OwnerAuthContext.Provider>
  );
}

export function useOwnerAuth() {
  const value = useContext(OwnerAuthContext);
  if (!value) throw new Error("useOwnerAuth must be used inside OwnerAuthProvider.");
  return value;
}
