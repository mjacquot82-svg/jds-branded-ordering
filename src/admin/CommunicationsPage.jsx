import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Bell, CheckCircle2, Megaphone, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { canAccessOwnerPath } from "../auth/ownerProductPermissions.js";
import { lunchSpecialAnnouncement } from "../services/announcementFormatting.js";
import { fetchOwnerCommunications, sendGeneralAnnouncement, sendLunchSpecial } from "../services/ownerCommunicationsApi.js";

const money = (cents) => new Intl.NumberFormat("en-CA", { currency: "CAD", style: "currency" }).format(cents / 100);

function Composer({ disabled, message, onMessageChange, title, onTitleChange, titleOptional = false, onSend, sending }) {
  return <div className="announcement-composer">
    {titleOptional ? <label>Title <span>Optional</span><input maxLength={80} onChange={(event) => onTitleChange(event.target.value)} placeholder="Holiday hours" value={title} /></label> : null}
    <label>Announcement message<textarea maxLength={280} onChange={(event) => onMessageChange(event.target.value)} rows={4} value={message} /></label>
    <small>{message.length}/280 characters</small>
    <div className="announcement-preview" aria-label="Customer notification preview">
      <span>Customer preview</span>
      {title ? <strong>{title}</strong> : null}
      <p>{message || "Your announcement preview will appear here."}</p>
    </div>
    <button className="primary-button" disabled={disabled || !message.trim() || sending} onClick={onSend} title={disabled ? "Push notifications are not release-enabled" : undefined} type="button">
      <Bell size={17} /> {sending?"Queueing…":"Send general announcement"}
    </button>
    {disabled ? <p className="announcement-provider-note"><AlertTriangle size={16} /> Push notifications are not connected yet. This draft has not been sent.</p> : null}
  </div>;
}

function LunchSpecialPreview({ disabled, message, onResend, onSend, resendAttempting, resendAvailable, sending }) {
  return <div className="announcement-composer announcement-generated-composer">
    <div className="announcement-preview" aria-label="Generated Lunch Special customer notification preview">
      <span>Customer preview · System generated</span>
      <p>{message}</p>
    </div>
    <p className="announcement-provider-note">This message uses the current Lunch Special name and catalog price and cannot be edited.</p>
    {resendAvailable ? <button className="secondary-button" disabled={disabled || !message || resendAttempting || sending} onClick={onResend} title={disabled ? "Push notifications are not release-enabled" : resendAttempting ? "Wait for the current delivery attempt to finish" : undefined} type="button">
      <Bell size={17} /> {sending?"Queueing…":resendAttempting?"Lunch Special notification is still attempting":"Resend Lunch Special notification"}
    </button> : <button className="primary-button" disabled={disabled || !message || sending} onClick={onSend} title={disabled ? "Push notifications are not release-enabled" : undefined} type="button">
      <Bell size={17} /> {sending?"Queueing…":"Send Lunch Special notification"}
    </button>}
    {disabled ? <p className="announcement-provider-note"><AlertTriangle size={16} /> Push notifications are not connected yet. This preview has not been sent.</p> : null}
  </div>;
}

export default function CommunicationsPage() {
  const { session } = useOwnerAuth();
  const owner = session?.role?.trim().toLowerCase() === "owner";
  const canOpenProducts = canAccessOwnerPath(session, "/admin/products");
  const [state, setState] = useState({ status: "loading", data: null, message: "" });
  const [generalTitle, setGeneralTitle] = useState("");
  const [generalMessage, setGeneralMessage] = useState("");
  const [sending,setSending]=useState("");
  const [actionMessage,setActionMessage]=useState("");
  const lunchInFlight = useRef(false);
  const load = useCallback(() => {
    const controller = new AbortController();
    setState((current) => ({ ...current, status: "loading", message: "" }));
    fetchOwnerCommunications({ signal: controller.signal })
      .then((data) => setState({ status: "ready", data, message: "" }))
      .catch((error) => {
        if (error?.name !== "AbortError") setState({ status: "error", data: null, message: error.message });
      });
    return controller;
  }, []);
  useEffect(() => { const controller = load(); return () => controller.abort(); }, [load]);
  useEffect(() => {
    if (!state.data?.activity?.some((item) => item.status === "queued" || item.status === "attempting")) return undefined;
    const timer = window.setTimeout(load, 15_000);
    return () => window.clearTimeout(timer);
  }, [load, state.data]);

  if (state.status === "loading" && !state.data) return <section className="page-section communication-page" aria-live="polite"><div className="page-heading"><h1>Customer announcements</h1><p>Loading today’s announcement workspace…</p></div><div className="communications-skeleton" /></section>;
  if (state.status === "error") return <section className="page-section communication-page"><div className="page-heading"><h1>Customer announcements</h1><p>{owner ? "Lunch Special and café updates for customers." : "Lunch Special notifications for customers."}</p></div><div className="communications-error" role="alert"><AlertTriangle /><div><strong>Announcement status is unavailable.</strong><p>{state.message}</p></div><button className="secondary-button" type="button" onClick={load}><RefreshCw size={16} /> Try again</button></div></section>;

  const { activity, health, lunch_special: special, summary } = state.data;
  const pushUnavailable = !summary.push_release_enabled;
  const lunchMessage = lunchSpecialAnnouncement(special);
  const resendAvailable = owner && summary.lunch_special_queued_today;
  async function sendLunch(){if(lunchInFlight.current)return;lunchInFlight.current=true;setSending("lunch");setActionMessage("");try{await sendLunchSpecial(session.csrf_token);setActionMessage("Lunch Special notification queued for eligible customers.");load()}catch(error){setActionMessage(error.message)}finally{lunchInFlight.current=false;setSending("")}}
  async function resendLunch(){if(lunchInFlight.current)return;lunchInFlight.current=true;const confirmed=window.confirm("Today’s Lunch Special notification was already queued.\n\nResending will send another notification to eligible customers.");if(!confirmed){lunchInFlight.current=false;return}setSending("lunch-resend");setActionMessage("");try{await sendLunchSpecial(session.csrf_token,{override:true,confirmOverride:true});setActionMessage("Owner-confirmed Lunch Special resend queued.");load()}catch(error){setActionMessage(error.message)}finally{lunchInFlight.current=false;setSending("")}}
  async function sendGeneral(){if(sending)return;setSending("general");setActionMessage("");try{await sendGeneralAnnouncement(session.csrf_token,{title:generalTitle.trim()||`${session.organization_name || "Café"} update`,body:generalMessage.trim(),targetRoute:"/"});setGeneralTitle("");setGeneralMessage("");setActionMessage("General announcement queued for eligible customers.");load()}catch(error){setActionMessage(error.message)}finally{setSending("")}}
  return <section className="page-section communication-page">
    <div className="page-heading communication-heading"><div><p className="eyebrow">Customer announcements</p><h1>Communications</h1><p>{owner ? "Prepare Lunch Special and occasional café announcements for customer push notifications." : "Prepare Lunch Special notifications for customers."}</p></div><button className="secondary-button" disabled={state.status === "loading"} type="button" onClick={load}><RefreshCw size={16} /> Refresh</button></div>

    <div className="communication-layout announcement-layout">
      <section className="communications-panel" aria-labelledby="lunch-announcement-heading">
        <div className="panel-heading"><div><h2 id="lunch-announcement-heading">Lunch Special announcement</h2><p>Products controls which item is selected as today’s Lunch Special.</p></div><Megaphone /></div>
        <div className="announcement-panel-body">
          {special ? <>
            <article className="announcement-special-card">
              <div><span>Today’s Lunch Special</span><h3>{special.name}</h3>{special.description ? <p>{special.description}</p> : null}</div>
              <strong>{money(special.price_cents)}</strong>
            </article>
            {special.warnings.length ? <div className="announcement-warning" role="alert"><AlertTriangle /><div><strong>Check the product before announcing it.</strong>{special.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div></div> : null}
            <LunchSpecialPreview disabled={pushUnavailable || !special.orderable} message={lunchMessage} onResend={resendLunch} onSend={sendLunch} resendAttempting={summary.lunch_special_attempting_today} resendAvailable={resendAvailable} sending={sending==="lunch" || sending==="lunch-resend"} />
          </> : <div className="communication-empty"><Megaphone /><h3>No Lunch Special selected</h3><p>Select a normal catalog product as the Lunch Special in Products before preparing an announcement.</p>{canOpenProducts ? <Link className="secondary-button" to="/admin/products">Open Products</Link> : <p>Ask an Owner to select today’s product in Products.</p>}</div>}
        </div>
      </section>

      <section className="communications-panel" aria-labelledby="health-heading">
        <div className="panel-heading"><div><h2 id="health-heading">Communication health</h2><p>Readiness for customer announcements.</p></div></div>
        <div className="health-list">{health.map((item) => <article key={item.key}><span className={`health-icon ${item.status}`}><Bell /></span><div><strong>{item.name}</strong><p>{item.detail}</p></div><span className={`status-pill ${item.status}`}>{item.status === "not_connected" ? "Not connected" : item.status}</span></article>)}</div>
      </section>
    </div>

    {actionMessage?<p className="form-status" aria-live="polite">{actionMessage}</p>:null}
    {owner ? <section className="communications-panel" aria-labelledby="general-announcement-heading"><div className="panel-heading"><div><h2 id="general-announcement-heading">General announcement</h2><p>Owner-only messages for closures, holidays, events, or café news.</p></div><Megaphone /></div><div className="announcement-panel-body"><Composer disabled={pushUnavailable} message={generalMessage} onMessageChange={setGeneralMessage} onSend={sendGeneral} sending={sending==="general"} onTitleChange={setGeneralTitle} title={generalTitle} titleOptional /></div></section> : null}

    <section className="communications-panel" aria-labelledby="activity-heading"><div className="panel-heading"><div><h2 id="activity-heading">Recent announcement activity</h2><p>Push-service acceptance is not a delivery or read receipt. Notification clicks are not currently measured.</p></div></div>{activity.length ? <div className="announcement-activity-list">{activity.map((item) => <article key={item.id}><div><span>{item.kind}</span><strong>{item.title}</strong><p>{item.message}</p></div><div><strong>{item.status}</strong><small>{new Date(item.occurred_at).toLocaleString()} · {item.sent_by}</small><small>Attempted {item.attempted} · Accepted {item.accepted} · Failed {item.failed} · Expired {item.expired} · Suppressed {item.suppressed}</small></div></article>)}</div> : <div className="communication-empty compact"><CheckCircle2 /><div><h3>No announcement activity</h3><p>No customer announcements have been queued.</p></div></div>}</section>
  </section>;
}
