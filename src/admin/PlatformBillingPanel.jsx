import { useEffect, useState } from "react";
import { billingStatusLabel, fetchPlatformBilling, formatDate, money } from "../services/billingApi.js";
import { packageName } from "../services/packages.js";

/** Platform admin: who's paid, who's behind, monthly recurring total. */
export default function PlatformBillingPanel() {
  const [data, setData] = useState(null);
  useEffect(() => { fetchPlatformBilling().then(setData).catch(() => setData(null)); }, []);
  if (!data) return null;
  return (
    <section className="operations-panel platform-billing" aria-label="Billing overview">
      <h2>Billing {data.enabled ? "" : "(switched off — everyone is free)"}</h2>
      <p><strong>Monthly recurring: {money(data.monthlyRecurringCents)} CAD</strong> · Paid up: {data.counts.paid} · Behind: {data.counts.behind} ({money(data.atRiskCents)} at risk) · Free (beta): {data.counts.exempt}</p>
      <div className="platform-table-wrap"><table><thead><tr><th>Shop</th><th>Package</th><th>Monthly</th><th>Status</th><th>Card</th><th>Next bill</th><th>Last paid</th></tr></thead><tbody>
        {data.shops.map((shop) => <tr key={shop.id}><td><strong>{shop.name}</strong></td><td>{packageName(shop.package) || "Not chosen"}{shop.pendingPackage ? ` → ${packageName(shop.pendingPackage)}` : ""}</td><td>{money(shop.monthlyAmountCents)}</td><td>{billingStatusLabel(shop.status)}{shop.orderingPaused ? " (ordering paused)" : ""}</td><td>{shop.hasCard ? "On file" : "—"}</td><td>{formatDate(shop.nextBillOn) || "—"}</td><td>{formatDate(shop.lastPaidAt) || "—"}</td></tr>)}
      </tbody></table></div>
    </section>
  );
}
