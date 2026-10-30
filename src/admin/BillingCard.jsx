import { useEffect, useRef, useState } from "react";
import { billingLines, changeBillingPackage, fetchOwnerBilling, loadSquareSdk, saveBillingCard } from "../services/billingApi.js";

/** Owner dashboard billing. Shows only "Free during the beta" while billing is off or the shop is exempt. */
export default function BillingCard({ csrfToken, canChange }) {
  const [view, setView] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [cardOpen, setCardOpen] = useState(false);
  const cardRef = useRef(null);
  useEffect(() => { fetchOwnerBilling().then(setView).catch(() => setView(null)); }, []);
  useEffect(() => {
    if (!cardOpen || !view?.cardForm) return undefined;
    let card; let cancelled = false;
    loadSquareSdk(view.cardForm.sdkUrl).then(async (Square) => {
      const payments = Square.payments(view.cardForm.applicationId, view.cardForm.locationId);
      card = await payments.card();
      if (!cancelled) { await card.attach("#jds-billing-card"); cardRef.current = card; }
    }).catch((reason) => setError(reason.message));
    return () => { cancelled = true; cardRef.current = null; card?.destroy?.(); };
  }, [cardOpen, view?.cardForm]);
  if (!view) return null;
  if (view.freeDuringBeta) {
    return <section className="operations-panel owner-billing-card" aria-label="Billing"><h2>Billing</h2><p>Free during the beta — you won't be charged.</p></section>;
  }
  async function saveCard() {
    setBusy(true); setError("");
    try {
      const result = await cardRef.current?.tokenize();
      if (result?.status !== "OK") throw new Error("Please check the card details.");
      setView(await saveBillingCard(result.token, view.package, csrfToken)); setCardOpen(false);
    } catch (reason) { setError(reason.message); } finally { setBusy(false); }
  }
  async function change(pkg) {
    setBusy(true); setError("");
    try { setView(await changeBillingPackage(pkg, view.extraLocations, csrfToken)); } catch (reason) { setError(reason.message); } finally { setBusy(false); }
  }
  const warn = view.status === "past_due" || view.orderingPaused;
  return (
    <section className={`operations-panel owner-billing-card${warn ? " is-warning" : ""}`} aria-label="Billing">
      <h2>Billing</h2>
      {billingLines(view).map((line) => <p key={line}>{line}</p>)}
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {canChange ? <div className="owner-billing-actions">
        {view.cardForm ? <button className="secondary-button" type="button" disabled={busy} onClick={() => setCardOpen(!cardOpen)}>{cardOpen ? "Close" : view.card ? "Update card" : "Add card"}</button> : null}
        {view.card ? <label>Package <select value={view.pendingPackage || view.package} disabled={busy} onChange={(event) => change(event.target.value)}>
          <option value="starter">Starter</option><option value="plus">Plus</option><option value="pro">Pro</option></select></label> : null}
      </div> : null}
      {cardOpen ? <div className="owner-billing-form"><div id="jds-billing-card" /><button className="primary-button" type="button" disabled={busy} onClick={saveCard}>{busy ? "Saving…" : "Save card"}</button><small>Your card is stored securely by Square, not by JDS.</small></div> : null}
    </section>
  );
}
