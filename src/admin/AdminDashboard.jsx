import { useCallback, useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { hasPermission, isOperationsAdministrator } from "../auth/ownerProductPermissions.js";
import { fetchOwnerCommunications } from "../services/ownerCommunicationsApi.js";
import { fetchOwnerOrderSummary } from "../services/ownerOrdersApi.js";
import { fetchOwnerSchedulingPreview } from "../services/ownerSchedulingApi.js";
import { CloverConnectionError, fetchCloverConnection, getCloverConnectUrl } from "../services/cloverService.js";
import { useCatalogProducts } from "../stores/catalogStore.js";

const money = (cents, currency) => new Intl.NumberFormat("en-CA", { currency, style: "currency" }).format(cents / 100);

export default function AdminDashboard() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { refreshSession, session } = useOwnerAuth();
  const administrator = isOperationsAdministrator(session);
  const canReadOrders = administrator || hasPermission(session, "orders.read");
  const canReadCatalog = administrator || hasPermission(session, "catalog.read");
  const canReadScheduling = administrator || hasPermission(session, "availability.manage");
  const canReadCommunications = administrator || hasPermission(session, "communications.announce");
  const canManageIntegrations = administrator || hasPermission(session, "integrations.manage");
  const [clover, setClover] = useState({ status: "loading" });
  const [orderSummary, setOrderSummary] = useState({ status: "loading" });
  const [ordering, setOrdering] = useState({ status: "loading" });
  const [communications, setCommunications] = useState({ status: "loading" });
  const { products } = useCatalogProducts({ enabled: canReadCatalog });
  const soldOut = products.filter((product) => product.published && !product.available).length;

  const loadCloverConnection = useCallback(() => {
    if (!canManageIntegrations) return;
    setClover({ status: "loading" });
    fetchCloverConnection()
      .then((connection) => setClover({ status: "ready", ...connection }))
      .catch((error) => {
        if (!(error instanceof CloverConnectionError)) setClover({ status: "server-error" });
        else if (error.status === 401) setClover({ status: "authentication-error" });
        else if (error.status === 403) setClover({ status: "permission-error" });
        else if (error.status === 404 || error.code === "clover_not_configured") setClover({ status: "configuration-error" });
        else if (error.code === "network_error") setClover({ status: "network-error" });
        else setClover({ status: "server-error" });
      });
  }, [canManageIntegrations]);

  useEffect(() => {
    loadCloverConnection();
    if (canReadOrders) fetchOwnerOrderSummary().then((value) => setOrderSummary({ status: "ready", ...value })).catch(() => setOrderSummary({ status: "error" }));
    if (canReadScheduling) fetchOwnerSchedulingPreview().then((value) => setOrdering({ status: "ready", ...value })).catch(() => setOrdering({ status: "error" }));
    if (canReadCommunications) fetchOwnerCommunications().then((value) => setCommunications({ status: "ready", ...value })).catch(() => setCommunications({ status: "error" }));
  }, [canReadCommunications, canReadOrders, canReadScheduling, loadCloverConnection]);

  const cloverDisplay = (() => {
    if (clover.status === "loading") return { detail: "Determining Clover connection...", heading: "Checking…" };
    if (clover.status === "ready" && !clover.configured) return { detail: "Clover configuration is incomplete.", heading: "Configuration needed" };
    if (clover.status === "ready" && clover.health === "reconnect_required") return { detail: `Environment: ${clover.environment}. Owner authorization is required again.`, heading: "Reconnect required" };
    if (clover.status === "ready" && clover.health === "refresh_required") return { detail: `Environment: ${clover.environment}. The access token will refresh on the next Clover operation.`, heading: "Refresh required" };
    if (clover.status === "ready" && clover.health === "expiring") return { detail: `Environment: ${clover.environment}. OAuth access is nearing refresh.`, heading: "Connected" };
    if (clover.status === "ready" && clover.connected) return { detail: `Environment: ${clover.environment}. Credential: ${clover.credential_source === "oauth" ? "OAuth" : "Sandbox private token"}.`, heading: "Connected" };
    if (clover.status === "ready") return { detail: "Clover is not connected.", heading: "Not connected" };
    if (clover.status === "authentication-error") return { detail: "Owner session expired. Please sign in again.", heading: "Sign-in required" };
    if (clover.status === "permission-error") return { detail: "Your account does not have permission to view Clover settings.", heading: "Permission required" };
    if (clover.status === "configuration-error") return { detail: "Clover configuration is incomplete.", heading: "Configuration needed" };
    if (clover.status === "network-error") return { detail: "Connection to the server failed.", heading: "Status unavailable" };
    return { detail: "Unable to determine Clover status.", heading: "Status unavailable" };
  })();

  async function handleSignInAgain() {
    try { await refreshSession(); loadCloverConnection(); }
    catch { navigate("/owner/login?returnTo=%2Fadmin", { replace: true }); }
  }

  return <section className="page-section operations-dashboard">
    <div className="page-heading operations-dashboard-heading"><div><p className="eyebrow">Operations Portal</p><h1>{administrator ? "Admin" : "Shift overview"}</h1><p>{administrator ? "Keep cafe orders, menu items, and availability easy to scan." : "See what needs attention before the next customer arrives."}</p></div></div>

    <div className="dashboard-grid">
      {canReadOrders ? <>
        <Link className="metric-card metric-card-link" to="/admin/orders"><span>Active paid orders</span><strong>{orderSummary.status === "loading" ? "—" : orderSummary.status === "ready" ? orderSummary.active_paid : "Unavailable"}</strong><p>{orderSummary.status === "ready" ? "Paid orders stay active until completed" : orderSummary.status === "loading" ? "Loading today’s queue…" : "Orders could not be loaded."}</p></Link>
        {administrator ? <Link className="metric-card metric-card-link" to="/admin/orders"><span>Today’s paid pickups</span><strong>{orderSummary.status === "loading" ? "—" : orderSummary.status === "ready" ? orderSummary.today_paid_count : "Unavailable"}</strong><p>{orderSummary.status === "ready" && orderSummary.today_paid_count === 0 ? "No paid pickup revenue yet" : orderSummary.status === "ready" && orderSummary.today_paid_revenue_cents !== null && orderSummary.currency ? `${money(orderSummary.today_paid_revenue_cents, orderSummary.currency)} paid pickup revenue` : orderSummary.status === "ready" ? "Revenue unavailable across mixed currencies" : orderSummary.status === "loading" ? "Calculating from paid orders…" : "Revenue could not be loaded."}</p></Link> : null}
      </> : null}
      {canReadCatalog ? <Link className="metric-card metric-card-link" to="/admin/products"><span>Sold-out products</span><strong>{soldOut}</strong><p>{soldOut ? "Review unavailable items" : "Everything published is available"}</p></Link> : null}
      {canReadScheduling ? <article className="metric-card"><span>Online ordering</span><strong>{ordering.status === "loading" ? "Checking…" : ordering.status === "error" ? "Unavailable" : ordering.ordering_status === "paused" ? "Paused" : ordering.ordering_available ? "Open" : "Closed"}</strong><p>{ordering.status === "ready" ? ordering.status_reason || "Current ordering status is live." : ordering.status === "loading" ? "Checking what customers can do…" : "Ordering status could not be loaded."}</p></article> : null}
      {canReadCommunications ? <Link className="metric-card metric-card-link" to="/admin/communications"><span>Communication warnings</span><strong>{communications.status === "loading" ? "—" : communications.status === "error" ? "Unavailable" : communications.summary.actionable_warnings}</strong><p>{communications.status === "ready" ? communications.summary.push_release_enabled ? "Review customer-announcement delivery health" : "Push announcements are not release-enabled yet" : communications.status === "loading" ? "Checking announcement readiness…" : "Communication health could not be loaded."}</p></Link> : null}
      {canManageIntegrations ? <article className="metric-card"><span>Clover</span><strong>{cloverDisplay.heading}</strong><p aria-live="polite">{searchParams.get("clover") === "connected" && clover.connected ? `Authorization completed. ${cloverDisplay.detail}` : cloverDisplay.detail}</p>{clover.status === "ready" && (!clover.connected || clover.health === "reconnect_required") ? <a className="secondary-button" href={getCloverConnectUrl()}>Connect Clover</a> : null}{clover.status === "authentication-error" ? <button className="secondary-button" type="button" onClick={handleSignInAgain}>Sign in again</button> : null}{!["loading", "ready", "authentication-error"].includes(clover.status) ? (
        <button className="secondary-button" type="button" onClick={loadCloverConnection}>
          Retry
        </button>
      ) : null}</article> : null}
    </div>
    {!administrator && !canReadOrders ? <p className="owner-page-message error"><AlertTriangle size={18} /> Your account cannot read the café order queue. Ask an Owner for operational access.</p> : null}
  </section>;
}
