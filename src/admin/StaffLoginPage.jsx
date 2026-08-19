import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { fetchStaffAccessOptions } from "../services/ownerAuthApi.js";

export default function StaffLoginPage() {
  const { session, staffLogin } = useOwnerAuth();
  const navigate = useNavigate();
  const [accounts, setAccounts] = useState([]); const [staffId, setStaffId] = useState("");
  const [pin, setPin] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { fetchStaffAccessOptions().then(setAccounts).catch(() => setError("Staff Access is unavailable.")); }, []);
  if (session?.role === "staff") return <Navigate replace to="/admin" />;
  async function submit(event) { event.preventDefault(); setBusy(true); setError(""); try { await staffLogin(staffId, pin); navigate("/admin", { replace: true }); } catch { setError("Staff member or PIN is invalid."); } finally { setBusy(false); } }
  return <section className="page-section compact-section"><div className="operations-panel owner-login-panel"><p className="eyebrow">Operations Portal</p><h1>Staff Access</h1><p>Choose your name and enter your individual PIN.</p><form className="owner-login-form" onSubmit={submit}><label>Staff member<select required value={staffId} onChange={(e) => setStaffId(e.target.value)}><option value="">Choose your name</option>{accounts.map((account) => <option key={account.id} value={account.id}>{account.display_name}</option>)}</select></label><label>PIN<input autoComplete="current-password" inputMode="numeric" pattern="[0-9]{6,10}" required type="password" value={pin} onChange={(e) => setPin(e.target.value)} /></label>{error ? <p className="form-error" role="alert">{error}</p> : null}<div className="login-action-row"><button className="primary-button" disabled={busy} type="submit">{busy ? "Signing in…" : "Sign in"}</button><Link className="secondary-button" to="/owner/login">Owner sign in</Link></div></form></div></section>;
}
