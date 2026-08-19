import { useEffect, useState } from "react";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { createStaffAccount, fetchStaffAccounts, resetStaffPin, setStaffAccessStatus } from "../services/staffManagementApi.js";

const blank = { name: "", pin: "", confirm: "" };

export default function StaffPage() {
  const { session } = useOwnerAuth();
  const [accounts, setAccounts] = useState([]);
  const [form, setForm] = useState(blank);
  const [reset, setReset] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    return fetchStaffAccounts()
      .then((value) => { setAccounts(value); setError(""); })
      .catch((value) => setError(value.message))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  async function submit(event) {
    event.preventDefault(); setError(""); setMessage("");
    if (form.pin !== form.confirm) return setError("PINs do not match.");
    try { await createStaffAccount(form.name, form.pin, session.csrf_token); setForm(blank); setMessage("Staff access created. The PIN will not be shown again."); await load(); }
    catch (value) { setError(value.message); }
  }

  async function saveReset(event) {
    event.preventDefault(); setError("");
    if (reset.pin !== reset.confirm) return setError("PINs do not match.");
    try { await resetStaffPin(reset.id, reset.pin, session.csrf_token); setReset(null); setMessage("PIN changed and existing sessions signed out."); await load(); }
    catch (value) { setError(value.message); }
  }

  async function toggle(account) {
    setError("");
    try { await setStaffAccessStatus(account.id, !account.active, session.csrf_token); setMessage(account.active ? "Staff access disabled." : "Staff access enabled."); await load(); }
    catch (value) { setError(value.message); }
  }

  return <section className="page-section"><div className="page-heading"><div><p className="eyebrow">Access management</p><h1>Staff</h1><p>Create individual café access, reset PINs, or disable access without deleting identity history.</p></div></div>
    {message ? <p className="owner-page-message success staff-access-message" role="status">{message}</p> : null}{error ? <p className="form-error" role="alert">{error}</p> : null}
    <div className="staff-access-grid"><section className="operations-panel"><h2>Staff access accounts</h2>{loading ? <p role="status">Loading Staff access accounts…</p> : <div className="staff-account-list">{accounts.map((account) => <article className="staff-account" key={account.id}><div><strong>{account.display_name}</strong><span className={account.active ? "status-active" : "status-disabled"}>{account.active ? "Active" : "Disabled"}</span></div><div className="staff-account-actions"><button className="secondary-button" type="button" onClick={() => setReset({ id: account.id, name: account.display_name, pin: "", confirm: "" })}>Reset PIN</button><button className="secondary-button" type="button" onClick={() => toggle(account)}>{account.active ? "Disable" : "Re-enable"}</button></div></article>)}</div>}</section>
    <section className="operations-panel"><h2>Create Staff access</h2><form className="owner-login-form" onSubmit={submit}><label>Display name<input required maxLength="200" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label><label>6–10 digit PIN<input autoComplete="new-password" inputMode="numeric" pattern="[0-9]{6,10}" required type="password" value={form.pin} onChange={(e) => setForm({ ...form, pin: e.target.value })} /></label><label>Confirm PIN<input autoComplete="new-password" inputMode="numeric" pattern="[0-9]{6,10}" required type="password" value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} /></label><button className="primary-button" type="submit">Create Staff access</button></form></section></div>
    {reset ? <div className="staff-reset-panel"><form className="operations-panel owner-login-form" onSubmit={saveReset}><h2>Set new PIN for {reset.name}</h2><p>The current PIN cannot be viewed. Saving signs this Staff member out everywhere.</p><label>New 6–10 digit PIN<input autoFocus inputMode="numeric" pattern="[0-9]{6,10}" required type="password" value={reset.pin} onChange={(e) => setReset({ ...reset, pin: e.target.value })} /></label><label>Confirm new PIN<input inputMode="numeric" pattern="[0-9]{6,10}" required type="password" value={reset.confirm} onChange={(e) => setReset({ ...reset, confirm: e.target.value })} /></label><div className="staff-account-actions"><button className="primary-button" type="submit">Set new PIN</button><button className="secondary-button" type="button" onClick={() => setReset(null)}>Cancel</button></div></form></div> : null}
  </section>;
}
