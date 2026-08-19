import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { UserRound } from "lucide-react";
import { useCustomerAuth } from "../auth/CustomerAuthContext.jsx";
import { fetchCustomerProfile, updateCustomerProfile } from "../services/customerAccountApi.js";
import { getCustomerErrorMessage } from "../services/customerMessages.js";
import { formatCustomerPhone, isCompleteCustomerPhone, normalizeCustomerPhone } from "../services/customerPhone.js";
import NotificationSettings from "../components/NotificationSettings.jsx";
import AccountLoyalty from "../components/AccountLoyalty.jsx";

export default function AccountPage() {
  const { logout, session, status: authStatus } = useCustomerAuth();
  const [profile, setProfile] = useState(null);
  const [message, setMessage] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  useEffect(() => {
    if (session) fetchCustomerProfile()
      .then((value) => setProfile({ ...value, phone: formatCustomerPhone(value.phone) }))
      .catch((error) => setMessage(getCustomerErrorMessage(error, "We couldn’t load your profile. Please try again.")));
  }, [session]);
  if (authStatus === "loading") return <section className="page-section compact-section"><p>Checking your account…</p></section>;
  if (!session) return <Navigate replace to="/account/sign-in" />;
  async function save(event) {
    event.preventDefault();
    if (isSaving) return;
    setMessage("");
    if (!isCompleteCustomerPhone(profile.phone)) {
      setMessage("Enter a complete 10-digit phone number.");
      return;
    }
    setIsSaving(true);
    try {
      const saved = await updateCustomerProfile({
        name: profile.name,
        phone: normalizeCustomerPhone(profile.phone),
        preferred_pickup_minutes: profile.preferred_pickup_minutes,
        preferred_pickup_notes: profile.preferred_pickup_notes,
      }, session.csrf_token);
      setProfile({ ...saved, phone: formatCustomerPhone(saved.phone) });
      setMessage("Profile saved.");
    } catch (error) {
      setMessage(getCustomerErrorMessage(error, "We couldn’t save your profile. Please try again."));
    } finally {
      setIsSaving(false);
    }
  }
  return (
    <section className="page-section ordering-page app-simple-page">
      <div className="ordering-top-card compact-app-heading"><div><p className="eyebrow">Cafe profile</p><h1>Account</h1><p>Your defaults for faster checkout.</p></div></div>
      <nav className="form-actions account-section-nav" aria-label="Account sections"><a className="secondary-button" href="#profile">Profile</a><a className="secondary-button" href="#loyalty">Loyalty</a><a className="secondary-button" href="#notifications">Notifications</a><Link className="secondary-button" to="/orders">My Orders</Link><button className="secondary-button" type="button" onClick={logout}>Logout</button></nav>
      {profile ? <form id="profile" className="content-block app-content-block product-form" aria-busy={isSaving} onSubmit={save}>
        <div className="account-card"><span className="account-avatar"><UserRound size={24} /></span><div><h2>Profile</h2><p>Manage the details saved to your account.</p></div></div>
        <label><span>Name</span><input disabled={isSaving} required value={profile.name} onChange={(event) => setProfile({ ...profile, name: event.target.value })} /></label>
        <label><span>Email</span><input disabled value={profile.email} /></label>
        <label><span>Phone</span><input autoComplete="tel" disabled={isSaving} inputMode="numeric" pattern="\(\d{3}\) \d{3}-\d{4}" placeholder="(519) 881-6869" required type="tel" value={profile.phone} onChange={(event) => setProfile({ ...profile, phone: formatCustomerPhone(event.target.value) })} /></label>
        <label><span>Preferred pickup lead time</span><select disabled={isSaving} value={profile.preferred_pickup_minutes ?? ""} onChange={(event) => setProfile({ ...profile, preferred_pickup_minutes: event.target.value ? Number(event.target.value) : null })}><option value="">No preference</option><option value="10">10 minutes</option><option value="20">20 minutes</option><option value="30">30 minutes</option><option value="60">1 hour</option></select></label>
        <label><span>Preferred pickup information</span><textarea disabled={isSaving} maxLength={500} rows="3" value={profile.preferred_pickup_notes} onChange={(event) => setProfile({ ...profile, preferred_pickup_notes: event.target.value })} /></label>
        <button className="primary-button" disabled={isSaving} type="submit">{isSaving ? "Saving…" : "Save profile"}</button>{message ? <p className="form-status" aria-live="polite">{message}</p> : null}
      </form> : <p>Loading your profile…</p>}
      <AccountLoyalty/>
      <NotificationSettings csrfToken={session.csrf_token}/>
    </section>
  );
}
