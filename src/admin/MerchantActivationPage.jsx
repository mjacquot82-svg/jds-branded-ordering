import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { ownerEntryPath } from "../auth/ownerAuthRouting.js";
import { inspectMerchantActivation } from "../services/ownerAuthApi.js";

export default function MerchantActivationPage() {
  const { activate, session } = useOwnerAuth();
  const navigate = useNavigate();
  const [secret] = useState(() => globalThis.location?.hash?.slice(1) || "");
  const [state, setState] = useState({ status: "loading" });
  const [password, setPassword] = useState("");

  useEffect(() => {
    if (!secret) { setState({ status: "error", message: "This activation link is invalid or expired." }); return; }
    globalThis.history?.replaceState?.(null, "", "/activate");
    inspectMerchantActivation(secret)
      .then((details) => setState({ status: "ready", details }))
      .catch((error) => setState({ status: "error", message: error.message }));
  }, [secret]);

  async function submit(event) {
    event.preventDefault();
    setState((current) => ({ ...current, status: "activating", message: "" }));
    try {
      const next = await activate(secret, state.details.intended_email, password);
      navigate(ownerEntryPath(next), { replace: true });
    } catch (error) {
      setState((current) => ({ ...current, status: "ready", message: error.message }));
    }
  }

  if (session) return <Navigate replace to={ownerEntryPath(session)} />;
  return <main className="merchant-activation-page">
    <header className="wizard-brand">JDS <span>Branded Ordering</span></header>
    <section className="merchant-activation-card">
      <p className="eyebrow">Your invitation</p>
      {state.status === "loading" ? <><h1>Preparing your app…</h1><p>Checking your secure invitation.</p></> : null}
      {state.status === "error" ? <><h1>Activation unavailable</h1><p role="alert">{state.message}</p></> : null}
      {["ready", "activating"].includes(state.status) ? <>
        <h1>Ready to build your ordering app?</h1>
        <p>Your account access is separate from your business setup. Sign in securely, then we’ll take you straight into the builder for <strong>{state.details.business_name}</strong>.</p>
        <form onSubmit={submit}>
          <label>Email<input readOnly type="email" value={state.details.intended_email} /></label>
          <label>Password<input autoComplete="current-password" required type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          {state.message ? <p className="form-error" role="alert">{state.message}</p> : null}
          <button className="primary-button" disabled={state.status === "activating"} type="submit">{state.status === "activating" ? "Opening your builder…" : "Build my app"}</button>
        </form>
      </> : null}
    </section>
  </main>;
}
