import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { ownerEntryPath } from "../auth/ownerAuthRouting.js";
import { enterDemo, fetchDemoPricing, signupDemo } from "../services/demoFunnelApi.js";

export default function BuildStoreLandingPage() {
  const { session, refreshSession } = useOwnerAuth();
  const navigate = useNavigate();
  const [pricing, setPricing] = useState(null);
  const [mode, setMode] = useState("signup");
  const [form, setForm] = useState({
    email: "",
    password: "",
    business_name: "",
    contact_name: "",
  });
  const [status, setStatus] = useState({ kind: "idle" });

  useEffect(() => {
    fetchDemoPricing()
      .then(setPricing)
      .catch(() => setPricing({
        amountDisplay: "CAD $150.00/month",
        jdsSalesTakePercent: 0,
        disclosure: "JDS takes 0% of your sales. Processor fees still apply.",
      }));
  }, []);

  if (session && ["owner", "manager"].includes(session.role)) {
    return <Navigate replace to={ownerEntryPath(session, "/admin/design")} />;
  }

  function update(field) {
    return (event) => setForm((current) => ({ ...current, [field]: event.target.value }));
  }

  async function submit(event) {
    event.preventDefault();
    setStatus({ kind: "working" });
    try {
      const result = mode === "signup"
        ? await signupDemo(form)
        : await enterDemo({ email: form.email, password: form.password });
      if (result.status === "verification_required") {
        setStatus({ kind: "verify", message: result.message });
        return;
      }
      await refreshSession?.();
      navigate("/admin/design", { replace: true });
    } catch (error) {
      setStatus({ kind: "error", message: error.message || "Unable to continue." });
    }
  }

  return (
    <main className="page-section build-store-landing">
      <header className="build-store-hero">
        <p className="eyebrow">JDS Branded Ordering</p>
        <h1>Build Your Store Free</h1>
        <p>
          Create a convincing version of your café — logo, colours, fonts, imagery, and a starter menu —
          then preview it on your phone. Real orders and payments stay locked until you request activation.
        </p>
        <ul className="build-store-points">
          <li>Start from a polished fictional Harbour &amp; Hearth café template (not a real shop)</li>
          <li>Save, return, and edit anytime with your secure account</li>
          <li>Go live later for about {pricing?.amountDisplay || "CAD $150/month"} — JDS takes 0% of sales</li>
        </ul>
        {pricing?.disclosure ? <p className="build-store-disclosure">{pricing.disclosure}</p> : null}
      </header>

      <section className="operations-panel build-store-card">
        <div className="login-action-row">
          <button className={mode === "signup" ? "primary-button" : "secondary-button"} type="button" onClick={() => setMode("signup")}>Create free demo</button>
          <button className={mode === "enter" ? "primary-button" : "secondary-button"} type="button" onClick={() => setMode("enter")}>I already started</button>
        </div>
        <form className="owner-login-form" onSubmit={submit}>
          {mode === "signup" ? (
            <>
              <label>Business name<input required maxLength={200} value={form.business_name} onChange={update("business_name")} placeholder="Your café name" /></label>
              <label>Your name<input maxLength={200} value={form.contact_name} onChange={update("contact_name")} placeholder="Optional" /></label>
            </>
          ) : null}
          <label>Email<input required type="email" autoComplete="email" value={form.email} onChange={update("email")} /></label>
          <label>Password<input required type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"} minLength={mode === "signup" ? 10 : 8} value={form.password} onChange={update("password")} /></label>
          {status.kind === "error" ? <p className="form-error" role="alert">{status.message}</p> : null}
          {status.kind === "verify" ? <p className="owner-page-message" role="status">{status.message}</p> : null}
          <button className="primary-button" disabled={status.kind === "working"} type="submit">
            {status.kind === "working" ? "Working…" : mode === "signup" ? "Start building free" : "Open my demo"}
          </button>
        </form>
        <p><Link to="/owner/login">Owner sign in</Link> for live merchants.</p>
      </section>
    </main>
  );
}
