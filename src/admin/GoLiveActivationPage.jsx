import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { fetchDemoStatus, recordDemoEvent, requestDemoActivation } from "../services/demoFunnelApi.js";

const PROCESSORS = [
  ["clover", "Clover"],
  ["square", "Square"],
  ["stripe", "Stripe"],
  ["moneris", "Moneris"],
  ["other", "Other"],
  ["not_sure", "Not sure yet"],
];

export default function GoLiveActivationPage({ embedded = false }) {
  const { session } = useOwnerAuth();
  const [status, setStatus] = useState({ kind: "loading" });
  const [form, setForm] = useState({
    business_name: "",
    contact_name: session?.display_name || "",
    email: session?.email || "",
    phone: "",
    city: "",
    desired_domain: "",
    processor_preference: "not_sure",
  });

  useEffect(() => {
    fetchDemoStatus()
      .then(async (demo) => {
        await recordDemoEvent("activation_viewed", {}, { csrfToken: session?.csrf_token }).catch(() => {});
        setStatus({ kind: "ready", demo });
        setForm((current) => ({
          ...current,
          business_name: current.business_name || demo.activationRequest?.businessName || "",
          email: current.email || session?.email || "",
        }));
      })
      .catch((error) => setStatus({ kind: "error", message: error.message }));
  }, [session?.csrf_token, session?.email]);

  if (status.kind === "loading") return <section className="page-section"><h1>Loading activation…</h1></section>;
  if (status.kind === "error") return <section className="page-section"><h1>Activation unavailable</h1><p role="alert">{status.message}</p></section>;

  const demo = status.demo;
  if (!demo.isProspect) {
    return (
      <section className="page-section">
        <h1>Your store is on the live plan</h1>
        <p>Continue to launch checks and payments when you are ready.</p>
        <Link className="primary-button" to={embedded ? "/setup/launch" : "/admin/launch"}>Open launch</Link>
      </section>
    );
  }

  async function submit(event) {
    event.preventDefault();
    setStatus({ kind: "ready", demo, working: true });
    try {
      const result = await requestDemoActivation(form, { csrfToken: session.csrf_token });
      const next = await fetchDemoStatus();
      setStatus({ kind: "ready", demo: next, submitted: result });
    } catch (error) {
      setStatus({ kind: "ready", demo, error: error.message });
    }
  }

  return (
    <section className={`page-section go-live-page${embedded ? " wizard-focus-card" : ""}`}>
      <header>
        <p className="eyebrow">{embedded ? "Step 8" : "Go live"}</p>
        <h1>{embedded ? "Ready to take real orders?" : "Start taking orders with JDS"}</h1>
        <p>
          Your demo design, menu, and media are preserved. Request activation and JDS will turn
          <strong> this exact store</strong> into a live customer on the {demo.pricing?.amountDisplay} plan.
        </p>
        <p className="build-store-disclosure">{demo.pricing?.disclosure}</p>
      </header>

      {demo.activationRequest ? (
        <div className="operations-panel">
          <h2>Activation requested</h2>
          <p>Status: <strong>{demo.activationRequest.status.replaceAll("_", " ")}</strong></p>
          <p>We have your lead for {demo.activationRequest.businessName}. Keep editing your demo anytime — nothing is discarded.</p>
          {embedded ? <div className="activation-next-links"><Link className="secondary-button" to="/setup/brand">Keep editing my demo</Link><Link className="secondary-button" to="/setup/preview">Open preview</Link></div> : <Link className="secondary-button" to="/admin/design">Back to Design Studio</Link>}
        </div>
      ) : (
        <form className="operations-panel owner-login-form" onSubmit={submit}>
          <h2>Request activation</h2>
          <label>Business name<input required value={form.business_name} onChange={(e) => setForm({ ...form, business_name: e.target.value })} /></label>
          <label>Contact name<input required value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} /></label>
          <label>Email<input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
          <label>Phone (optional)<input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
          <label>City / location<input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} /></label>
          <label>Desired domain (optional)<input value={form.desired_domain} onChange={(e) => setForm({ ...form, desired_domain: e.target.value })} placeholder="orders.yourcafe.ca" /></label>
          <label>Payment processor preference
            <select value={form.processor_preference} onChange={(e) => setForm({ ...form, processor_preference: e.target.value })}>
              {PROCESSORS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <p className="build-store-disclosure">Processor preference is information only — this form does not connect Square/Stripe/Moneris.</p>
          {status.error ? <p className="form-error" role="alert">{status.error}</p> : null}
          <button className="primary-button" disabled={status.working} type="submit">{status.working ? "Sending…" : "Request activation"}</button>
        </form>
      )}
    </section>
  );
}
