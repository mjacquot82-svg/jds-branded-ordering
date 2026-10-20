import { useEffect, useState } from "react";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { ORDER_SETTINGS_DEFAULTS, fetchOrderSettings, saveOrderSettings } from "../services/ownerOrderSettingsApi.js";

function toDraft(value) {
  return {
    pay_at_pickup_enabled: value.pay_at_pickup_enabled,
    pay_at_pickup_min_completed_orders: value.pay_at_pickup_min_completed_orders,
    max_total_dollars: (value.pay_at_pickup_max_total_cents / 100).toFixed(2),
    new_order_alert_email: value.new_order_alert_email || "",
  };
}

/** Pay at pickup + new-order email alerts. Off unless the shop turns it on. */
export default function OrderSettingsPanel({ onSaved }) {
  const { session } = useOwnerAuth();
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    fetchOrderSettings().then((value) => setDraft(toDraft(value))).catch(() => setDraft(toDraft(ORDER_SETTINGS_DEFAULTS)));
  }, []);
  if (!draft) return <section className="owner-settings-card order-settings-card"><h2>Payments at pickup &amp; order alerts</h2><p>Loading…</p></section>;
  const update = (field, value) => { setDraft({ ...draft, [field]: value }); setMessage(""); };
  async function submit(event) {
    event.preventDefault();
    setBusy(true); setError(""); setMessage("");
    try {
      const saved = await saveOrderSettings(draft, session?.csrf_token);
      setDraft(toDraft(saved));
      setMessage("Order settings saved.");
      onSaved?.(saved);
    } catch (saveError) { setError(saveError.message); }
    finally { setBusy(false); }
  }
  return (
    <section className="owner-settings-card order-settings-card" aria-labelledby="order-settings-heading">
      <h2 id="order-settings-heading">Pay at pickup &amp; order alerts</h2>
      <form onSubmit={submit}>
        <label className="order-settings-toggle">
          <input checked={draft.pay_at_pickup_enabled} type="checkbox" onChange={(event) => update("pay_at_pickup_enabled", event.target.checked)} />
          <span>Let customers order now and pay at the counter</span>
        </label>
        <p>To protect you from no-shows, only customers with a verified email and enough past completed orders can choose it, orders have a maximum total, and anyone who doesn’t show up loses the option.</p>
        <div className="preference-fields">
          <label><span>Completed orders needed first</span>
            <input disabled={!draft.pay_at_pickup_enabled} inputMode="numeric" max="100" min="0" type="number" value={draft.pay_at_pickup_min_completed_orders} onChange={(event) => update("pay_at_pickup_min_completed_orders", event.target.value)} />
            <small>Customers must have picked up this many paid orders before.</small></label>
          <label><span>Maximum order total ($)</span>
            <input disabled={!draft.pay_at_pickup_enabled} inputMode="decimal" max="1000" min="1" step="0.01" type="number" value={draft.max_total_dollars} onChange={(event) => update("max_total_dollars", event.target.value)} />
            <small>Bigger orders must be paid online.</small></label>
          <label><span>Email me new orders at</span>
            <input autoComplete="email" maxLength={320} placeholder="orders@yourcafe.com" type="email" value={draft.new_order_alert_email} onChange={(event) => update("new_order_alert_email", event.target.value)} />
            <small>Optional. An email goes out for each new order. Orders still work if email is down.</small></label>
        </div>
        <button className="primary-button" disabled={busy} type="submit">{busy ? "Saving…" : "Save order settings"}</button>
        {message ? <p className="owner-page-message success" role="status">{message}</p> : null}
        {error ? <p className="owner-page-message error" role="alert">{error}</p> : null}
      </form>
    </section>
  );
}
