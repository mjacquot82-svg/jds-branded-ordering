import { useEffect, useState } from "react";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { fetchBusinessProfile, fetchOnboarding, saveBusinessProfile, saveOnboarding } from "../services/designStudioApi.js";

const steps = [
  ["business", "Business details", "Name, address, and customer contact details"],
  ["storefront", "Storefront address", "Your unique JDS storefront name"],
  ["hours", "Ordering hours", "Weekly hours and planned closures"],
  ["fulfillment", "Pickup setup", "Lead time, instructions, and fulfillment wording"],
  ["design", "Storefront design", "Template, colors, typography, and imagery"],
  ["catalog", "Menu", "Products, choices, pricing, and availability"],
  ["clover", "Clover readiness", "Connection status for checkout; not required while setting up"],
];

export default function OnboardingPage() {
  const { session } = useOwnerAuth();
  const [state, setState] = useState(null); const [message, setMessage] = useState(""); const [saving, setSaving] = useState(false);
  const [profile, setProfile] = useState(null);
  useEffect(() => { Promise.all([fetchOnboarding(), fetchBusinessProfile()]).then(([progress,business])=>{setState(progress);setProfile(business);}).catch((error) => setMessage(error.message)); }, []);
  if (!state || !profile) return <section className="page-section"><h1>Business setup</h1><p>{message || "Loading your progress…"}</p></section>;
  const completed = new Set(state.completedSteps);
  const toggle = (key) => setState((current) => ({ ...current, completedSteps: completed.has(key) ? current.completedSteps.filter((item) => item !== key) : [...current.completedSteps, key], currentStep: key }));
  const field = (key) => (event) => setProfile((current)=>({...current,[key]:event.target.value}));
  async function save() { try { setSaving(true); const allDone=steps.every(([key])=>completed.has(key)); const [next,business]=await Promise.all([saveOnboarding({ revision:state.revision, current_step:allDone?"complete":state.currentStep, completed_steps:state.completedSteps },session.csrf_token),saveBusinessProfile(profile,session.csrf_token)]);setState(next);setProfile(business);setMessage("Setup progress saved."); } catch(error){setMessage(error.message);} finally{setSaving(false);} }
  return <section className="page-section onboarding-page"><header><p className="eyebrow">Resumable setup</p><h1>Business setup</h1><p>Complete each area at your pace. Your storefront stays private until JDS readiness checks pass.</p></header>
    <div className="onboarding-progress" aria-label={`${completed.size} of ${steps.length} setup areas complete`}><span style={{width:`${completed.size/steps.length*100}%`}} /></div>
    <fieldset className="business-basics"><legend>Business and pickup details</legend><label>Display name<input value={profile.display_name} onChange={field("display_name")}/></label><label>Contact email<input type="email" value={profile.contact_email||""} onChange={field("contact_email")}/></label><label>Phone<input value={profile.phone||""} onChange={field("phone")}/></label><label>Timezone<input value={profile.timezone} onChange={field("timezone")}/></label><label>Pickup wording<input value={profile.fulfillment_wording} onChange={field("fulfillment_wording")}/></label><label>Pickup instructions<textarea value={profile.pickup_instructions} onChange={field("pickup_instructions")}/></label></fieldset>
    <div className="onboarding-checklist">{steps.map(([key,title,note])=><label key={key}><input type="checkbox" checked={completed.has(key)} onChange={()=>toggle(key)}/><span><strong>{title}</strong><small>{note}</small></span></label>)}</div>
    <div className="design-actions"><button className="primary-button" type="button" disabled={saving} onClick={save}>{saving?"Saving…":"Save progress"}</button></div>
    {message ? <p className="owner-page-message" aria-live="polite">{message}</p> : null}
    {state.state === "complete" && !state.publicReady ? <p className="readiness-note">Setup is complete. Ordering remains private until catalog, scheduling, and payment readiness are verified.</p> : null}
  </section>;
}
