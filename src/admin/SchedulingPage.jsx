import { useEffect, useState } from "react";
import { AlertTriangle, CalendarDays, CheckCircle2, Clock3, RefreshCw } from "lucide-react";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import {
  createOwnerClosure,
  deleteOwnerClosure,
  fetchOwnerScheduling,
  fetchOwnerSchedulingPreview,
  updateOwnerClosure,
  updateOwnerHours,
  updateOwnerOrdering,
  updateOwnerPreferences,
} from "../services/ownerSchedulingApi.js";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const DEFAULT_OPEN = "07:00";
const DEFAULT_CLOSE = "15:00";
const EMPTY_CLOSURE = { business_date: "", reopens_on: "", reason: "" };

function normalizeHours(hours = []) {
  return DAYS.map((_, weekday) => {
    const entry = hours.find((item) => item.weekday === weekday);
    return {
      weekday,
      is_closed: entry?.is_closed ?? true,
      opens_at: entry?.opens_at?.slice(0, 5) || DEFAULT_OPEN,
      closes_at: entry?.closes_at?.slice(0, 5) || DEFAULT_CLOSE,
    };
  });
}

function formatTime(value, timezone) {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat("en-CA", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: timezone,
  }).format(new Date(value));
}

function formatDate(value, timezone, options = {}) {
  return new Intl.DateTimeFormat("en-CA", {
    day: "numeric",
    month: "long",
    timeZone: timezone,
    ...options,
  }).format(new Date(`${value}T12:00:00`));
}

function nextPickupText(preview) {
  if (!preview.earliest_pickup_at) return "Not available";
  const pickup = new Date(preview.earliest_pickup_at);
  const now = new Date(preview.server_now);
  const dateFormatter = new Intl.DateTimeFormat("en-CA", {
    dateStyle: "short",
    timeZone: preview.business_timezone,
  });
  const pickupDate = dateFormatter.format(pickup);
  const today = dateFormatter.format(now);
  const tomorrow = dateFormatter.format(new Date(now.getTime() + 86400000));
  const time = formatTime(preview.earliest_pickup_at, preview.business_timezone);
  if (pickupDate === today) return time;
  if (pickupDate === tomorrow) return `Tomorrow at ${time}`;
  return `${new Intl.DateTimeFormat("en-CA", { month: "long", day: "numeric", timeZone: preview.business_timezone }).format(pickup)} at ${time}`;
}

function friendlyTimezone(value) {
  return value?.replaceAll("_", " ").replace("America/", "") || "Not available";
}

function includeCurrent(options, current) {
  return [...new Set([...options, current])].sort((first, second) => first - second);
}

function previewCopy(preview) {
  if (preview.ordering_status === "paused") {
    return { headline: "ONLINE ORDERING IS PAUSED", explanation: "Customers cannot place online orders.", tone: "paused" };
  }
  if (preview.ordering_available) {
    return { headline: "ONLINE ORDERING IS OPEN", explanation: "Customers can order now.", tone: "open" };
  }
  return { headline: "ONLINE ORDERING IS CLOSED", explanation: preview.status_reason || "Customers cannot place online orders.", tone: "closed" };
}

function ClosureForm({ initialValue = EMPTY_CLOSURE, onCancel, onSave, saving }) {
  const [value, setValue] = useState(initialValue);
  return (
    <form className="owner-closure-form" onSubmit={(event) => { event.preventDefault(); onSave(value); }}>
      <label><span>First Day Closed</span><input required type="date" value={value.business_date} onChange={(event) => setValue({ ...value, business_date: event.target.value })} /></label>
      <label><span>Reopen On <small>(optional)</small></span><input min={value.business_date || undefined} type="date" value={value.reopens_on || ""} onChange={(event) => setValue({ ...value, reopens_on: event.target.value })} /></label>
      <label className="closure-reason-field"><span>Reason <small>(optional)</small></span><input maxLength="500" placeholder="Christmas Day" type="text" value={value.reason || ""} onChange={(event) => setValue({ ...value, reason: event.target.value })} /></label>
      <p className="form-helper">Leave “Reopen On” blank if the café is closed for one day.</p>
      <div className="form-actions"><button className="primary-button" disabled={saving} type="submit">{saving ? "Saving…" : "Save Closure"}</button><button className="secondary-button" disabled={saving} type="button" onClick={onCancel}>Cancel</button></div>
    </form>
  );
}

export default function SchedulingPage() {
  const { session } = useOwnerAuth();
  const [data, setData] = useState(null);
  const [hours, setHours] = useState([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [showClosureForm, setShowClosureForm] = useState(false);
  const [editingClosure, setEditingClosure] = useState(null);
  const [showPastClosures, setShowPastClosures] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);

  function adopt(next) {
    setData(next);
    setHours(normalizeHours(next.hours));
    setLastUpdated(new Date());
  }

  useEffect(() => {
    fetchOwnerScheduling().then(adopt).catch((loadError) => setError(loadError.message));
  }, []);

  async function perform(key, action, success) {
    setBusy(key); setError(""); setStatus("");
    try {
      const next = await action();
      adopt(next);
      setStatus(success);
      return true;
    } catch (actionError) {
      setError(actionError.message);
      return false;
    } finally { setBusy(""); }
  }

  async function chooseOrdering(mode) {
    if (mode === data.ordering_mode) return;
    const prompt = mode === "force_open"
      ? "Start accepting online orders now? Customers will be able to order even if the café is outside its regular hours."
      : mode === "force_closed"
        ? "Pause online orders now? Customers will not be able to place new orders."
        : null;
    if (prompt && !window.confirm(prompt)) return;
    const label = mode === "force_open" ? "Online orders are temporarily open." : mode === "force_closed" ? "Online orders paused." : "Online ordering now uses business hours.";
    await perform("ordering", () => updateOwnerOrdering(mode, session.csrf_token), label);
  }

  async function refreshPreview() {
    setBusy("preview"); setError("");
    try {
      const preview = await fetchOwnerSchedulingPreview();
      setData((current) => ({ ...current, preview }));
      setLastUpdated(new Date());
    } catch (refreshError) { setError(refreshError.message); }
    finally { setBusy(""); }
  }

  function updateHour(weekday, changes) {
    setHours((current) => current.map((entry) => entry.weekday === weekday ? { ...entry, ...changes } : entry));
  }

  async function saveHours(event) {
    event.preventDefault();
    await perform("hours", () => updateOwnerHours(hours.map((entry) => ({ ...entry, opens_at: entry.is_closed ? null : entry.opens_at, closes_at: entry.is_closed ? null : entry.closes_at })), session.csrf_token), "Business hours saved.");
  }

  async function saveClosure(value) {
    const payload = { ...value, reopens_on: value.reopens_on || null, reason: value.reason.trim() || null };
    const action = editingClosure
      ? () => updateOwnerClosure(editingClosure.id, payload, session.csrf_token)
      : () => createOwnerClosure(payload, session.csrf_token);
    if (await perform("closure", action, editingClosure ? "Closure updated." : "Closure added.")) {
      setShowClosureForm(false); setEditingClosure(null);
    }
  }

  async function removeClosure(closure) {
    if (!window.confirm("Remove this closure? Customers may be able to choose pickup on this date.")) return;
    await perform(`delete-${closure.id}`, () => deleteOwnerClosure(closure.id, session.csrf_token), "Closure removed.");
  }

  if (!data) return <section className="page-section"><div className="operations-panel"><h1>Scheduling</h1><p>{error || "Loading your café schedule…"}</p></div></section>;

  const preview = data.preview;
  const hero = previewCopy(preview);
  const businessDate = preview.server_now.slice(0, 10);
  const upcomingClosures = data.closures.filter((closure) => (closure.reopens_on || closure.business_date) >= businessDate);
  const pastClosures = data.closures.filter((closure) => (closure.reopens_on || closure.business_date) < businessDate);
  const overrideActive = data.ordering_mode !== "schedule";

  return (
    <section className="page-section owner-scheduling-page">
      <div className="page-heading"><p className="eyebrow">Owner workspace</p><h1>Scheduling</h1><p>Manage when customers can order and when pickups are available.</p></div>

      {overrideActive ? <div className={`owner-override-notice ${data.ordering_mode === "force_closed" ? "paused" : "open"}`} role="status"><AlertTriangle aria-hidden="true" size={22} /><div><strong>{data.ordering_mode === "force_closed" ? "Online orders are temporarily paused." : "Online orders are temporarily being accepted."}</strong><p>Regular business hours are being overridden until you change it.</p></div><button className="secondary-button" disabled={busy === "ordering"} type="button" onClick={() => chooseOrdering("schedule")}>Return to Business Hours</button></div> : null}

      <section className="owner-settings-card" aria-labelledby="online-ordering-heading">
        <div className="owner-card-heading"><div><h2 id="online-ordering-heading">Online Ordering</h2><p>Choose when to accept online orders.</p></div></div>
        <div className="ordering-mode-options">
          {[
            ["schedule", "Use Business Hours", "Recommended", "Accept orders while the café is open and pause them while it is closed."],
            ["force_open", "Temporarily Accept Orders", null, "Accept online orders even if the café is currently closed."],
            ["force_closed", "Temporarily Pause Orders", null, "Stop accepting new online orders until you return to business hours."],
          ].map(([value, label, badge, description]) => <label className={`ordering-mode-option ${data.ordering_mode === value ? "selected" : ""}`} key={value}><input checked={data.ordering_mode === value} disabled={busy === "ordering"} name="ordering-mode" type="radio" onChange={() => chooseOrdering(value)} /><span><strong>{label}{badge ? <small>{badge}</small> : null}</strong><span>{description}</span>{value !== "schedule" ? <em>This overrides regular business hours until you change it.</em> : null}</span></label>)}
        </div>
      </section>

      <section className={`owner-preview-card ${hero.tone}`} aria-labelledby="customer-preview-heading">
        <div className="preview-title-row"><div><p className="eyebrow">What Customers See Right Now</p><h2 id="customer-preview-heading"><CheckCircle2 aria-hidden="true" size={28} />{hero.headline}</h2><p>{hero.explanation}</p></div><button className="preview-refresh-button" disabled={busy === "preview"} type="button" onClick={refreshPreview}><RefreshCw aria-hidden="true" size={17} className={busy === "preview" ? "spinning" : ""} />Refresh</button></div>
        <div className="next-pickup-hero"><span>Next Pickup</span><strong>{nextPickupText(preview)}</strong></div>
        <dl className="preview-details"><div><dt>Shop Status</dt><dd>{preview.shop_open ? "Open" : "Closed"}</dd></div><div><dt>Online Ordering</dt><dd>{preview.ordering_available ? "Enabled" : "Disabled"}</dd></div><div><dt>Earliest Pickup</dt><dd>{nextPickupText(preview)}</dd></div><div><dt>Business Timezone</dt><dd>{friendlyTimezone(preview.business_timezone)}</dd></div><div><dt>Current Business Time</dt><dd>{formatTime(preview.server_now, preview.business_timezone)}</dd></div><div><dt>Last Updated</dt><dd>{lastUpdated ? formatTime(lastUpdated.toISOString(), preview.business_timezone) : "Not available"}</dd></div></dl>
        {preview.status_reason ? <p className="preview-reason"><strong>Reason</strong>{preview.status_reason}</p> : null}
        {overrideActive ? <button className="secondary-button" disabled={busy === "ordering"} type="button" onClick={() => chooseOrdering("schedule")}>Return to Business Hours</button> : null}
      </section>

      <section className="owner-settings-card" aria-labelledby="business-hours-heading">
        <div className="owner-card-heading"><div><h2 id="business-hours-heading">Business Hours</h2><p>Set the café’s regular opening and closing times.</p></div><button className="secondary-button compact-button" type="button" onClick={() => { const monday = hours[0]; setHours((current) => current.map((entry) => entry.weekday <= 4 ? { ...entry, is_closed: monday.is_closed, opens_at: monday.opens_at, closes_at: monday.closes_at } : entry)); }}>Copy Monday’s Hours to Weekdays</button></div>
        <form onSubmit={saveHours}><div className="business-hours-list">{hours.map((entry) => <div className={`business-hour-row ${entry.is_closed ? "closed" : ""}`} key={entry.weekday}><strong>{DAYS[entry.weekday]}</strong><label className="day-status-control"><input checked={!entry.is_closed} type="checkbox" onChange={(event) => updateHour(entry.weekday, { is_closed: !event.target.checked })} /><span>{entry.is_closed ? "Closed" : "Open"}</span></label>{!entry.is_closed ? <div className="business-time-fields"><label><span>Opens</span><input required type="time" value={entry.opens_at} onChange={(event) => updateHour(entry.weekday, { opens_at: event.target.value })} /></label><span aria-hidden="true">to</span><label><span>Closes</span><input required type="time" value={entry.closes_at} onChange={(event) => updateHour(entry.weekday, { closes_at: event.target.value })} /></label></div> : <span className="closed-day-note">No pickups</span>}</div>)}</div><button className="primary-button" disabled={busy === "hours"} type="submit">{busy === "hours" ? "Saving…" : "Save Business Hours"}</button></form>
      </section>

      <section className="owner-settings-card" aria-labelledby="closures-heading">
        <div className="owner-card-heading"><div><h2 id="closures-heading">Holiday &amp; Closure Dates</h2><p>Add holidays, vacations, or other dates when the café will be closed.</p></div><button className="secondary-button" type="button" onClick={() => { setEditingClosure(null); setShowClosureForm(true); }}>Add Closure</button></div>
        {showClosureForm ? <ClosureForm key={editingClosure?.id || "new"} initialValue={editingClosure ? { business_date: editingClosure.business_date, reopens_on: editingClosure.reopens_on || "", reason: editingClosure.reason || "" } : EMPTY_CLOSURE} saving={busy === "closure"} onCancel={() => { setShowClosureForm(false); setEditingClosure(null); }} onSave={saveClosure} /> : null}
        <div className="closure-list">{upcomingClosures.length ? upcomingClosures.map((closure) => <article className="closure-row" key={closure.id}><CalendarDays aria-hidden="true" size={20} /><div><strong>{formatDate(closure.business_date, data.timezone)}{closure.reopens_on ? ` – ${formatDate(new Date(new Date(`${closure.reopens_on}T12:00:00`).getTime() - 86400000).toISOString().slice(0, 10), data.timezone)}` : ""}</strong><span>{closure.reason || "Scheduled closure"}</span>{closure.reopens_on ? <small>Reopens {formatDate(closure.reopens_on, data.timezone)}</small> : null}</div><div className="closure-actions"><button type="button" onClick={() => { setEditingClosure(closure); setShowClosureForm(true); }}>Edit</button><button disabled={busy === `delete-${closure.id}`} type="button" onClick={() => removeClosure(closure)}>Remove</button></div></article>) : <p className="empty-owner-state">No upcoming closures.</p>}</div>
        {pastClosures.length ? <details open={showPastClosures} onToggle={(event) => setShowPastClosures(event.currentTarget.open)} className="past-closures"><summary>Show Past Closures ({pastClosures.length})</summary><div className="closure-list">{pastClosures.map((closure) => <article className="closure-row" key={closure.id}><CalendarDays aria-hidden="true" size={20} /><div><strong>{formatDate(closure.business_date, data.timezone)}</strong><span>{closure.reason || "Scheduled closure"}</span></div></article>)}</div></details> : null}
      </section>

      <details className="owner-settings-card scheduling-preferences">
        <summary><span><strong>Scheduling Preferences</strong><small>Minimum notice: {data.minimum_lead_time_minutes} minutes · Pickup times: every {data.pickup_interval_minutes} minutes · Advance orders: up to {data.maximum_advance_days} days</small></span><Clock3 aria-hidden="true" size={20} /></summary>
        <form onSubmit={async (event) => { event.preventDefault(); const form = new FormData(event.currentTarget); await perform("preferences", () => updateOwnerPreferences({ minimum_lead_time_minutes: Number(form.get("notice")), pickup_interval_minutes: Number(form.get("spacing")), maximum_advance_days: Number(form.get("advance")) }, session.csrf_token), "Scheduling preferences saved."); }}><p>These settings control the pickup times offered to customers.</p><div className="preference-fields"><label><span>Minimum Notice Before Pickup</span><select defaultValue={data.minimum_lead_time_minutes} name="notice">{includeCurrent([0, 5, 10, 15, 20, 30, 45, 60, 90, 120], data.minimum_lead_time_minutes).map((value) => <option key={value} value={value}>{value === 0 ? "No minimum notice" : value < 60 ? `${value} minutes` : value === 60 ? "1 hour" : Number.isInteger(value / 60) ? `${value / 60} hours` : `${value} minutes`}</option>)}</select><small>The shortest amount of notice you need before an order can be picked up.</small></label><label><span>Pickup Time Spacing</span><select defaultValue={data.pickup_interval_minutes} name="spacing">{includeCurrent([5, 10, 15, 20, 30, 60], data.pickup_interval_minutes).map((value) => <option key={value} value={value}>Every {value} minutes</option>)}</select><small>How often customers can choose a pickup time.</small></label><label><span>How Far Ahead Customers Can Order</span><select defaultValue={data.maximum_advance_days} name="advance">{includeCurrent([1, 2, 3, 7, 14, 30, 60, 90], data.maximum_advance_days).map((value) => <option key={value} value={value}>Up to {value} {value === 1 ? "day" : "days"} ahead</option>)}</select><small>The furthest date customers can choose for pickup.</small></label></div><button className="primary-button" disabled={busy === "preferences"} type="submit">{busy === "preferences" ? "Saving…" : "Save Scheduling Preferences"}</button></form>
      </details>

      {status ? <p className="owner-page-message success" role="status">{status}</p> : null}{error ? <p className="owner-page-message error" role="alert">{error}</p> : null}
    </section>
  );
}
