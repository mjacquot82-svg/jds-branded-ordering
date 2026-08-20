import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { fetchBusinessProfile, fetchOnboarding, fetchReadiness, fetchStorefront, recheckReadiness, saveBusinessProfile, saveOnboarding, saveStorefront } from "../services/designStudioApi.js";

const steps = [
  { key:"business", title:"Business details", note:"Name and customer contact details", to:"/admin/setup#business" },
  { key:"storefront", title:"Storefront address", note:"Choose your hosted ordering address", to:"/admin/setup#business" },
  { key:"hours", title:"Ordering hours", note:"Set weekly hours and planned closures", to:"/admin/scheduling" },
  { key:"fulfillment", title:"Pickup setup", note:"Set lead time, instructions, and ordering availability", to:"/admin/scheduling" },
  { key:"design", title:"Storefront design", note:"Choose a template, branding, and imagery", to:"/admin/design" },
  { key:"catalog", title:"Menu", note:"Add and publish at least one product", to:"/admin/products" },
  { key:"clover", title:"Clover readiness", note:"Use a safe sandbox connection while setting up", to:"/admin" },
];

export default function OnboardingPage() {
  const { session } = useOwnerAuth();
  const [state, setState] = useState(null); const [message, setMessage] = useState(""); const [saving, setSaving] = useState(false);
  const [profile, setProfile] = useState(null);
  const [readiness,setReadiness]=useState(null);const [storefront,setStorefront]=useState(null);const [slug,setSlug]=useState("");
  useEffect(() => { Promise.all([fetchOnboarding(), fetchBusinessProfile(),fetchReadiness(),fetchStorefront()]).then(([progress,business,checks,shop])=>{setState(progress);setProfile(business);setReadiness(checks);setStorefront(shop);setSlug(shop.slug);}).catch((error) => setMessage(error.message)); }, []);
  if (!state || !profile) return <section className="page-section"><h1>Business setup</h1><p>{message || "Loading your progress…"}</p></section>;
  const completed = new Set(state.completedSteps);
  const field = (key) => (event) => setProfile((current)=>({...current,[key]:event.target.value}));
  async function save() { try { setSaving(true); const allDone=steps.every(({key})=>completed.has(key));await saveBusinessProfile(profile,session.csrf_token);if(slug!==storefront.slug)await saveStorefront(slug,session.csrf_token);await saveOnboarding({ revision:state.revision, current_step:allDone?"complete":state.currentStep, completed_steps:state.completedSteps },session.csrf_token);await recheckReadiness(session.csrf_token);const [next,business,checks,shop]=await Promise.all([fetchOnboarding(),fetchBusinessProfile(),fetchReadiness(),fetchStorefront()]);setState(next);setProfile(business);setReadiness(checks);setStorefront(shop);setSlug(shop.slug);setMessage("Business details saved. Your launch checks have been refreshed."); } catch(error){setMessage(error.message);} finally{setSaving(false);} }
  const nextStep=steps.find(({key})=>!completed.has(key));
  return <section className="page-section onboarding-page"><header><p className="eyebrow">Resumable setup</p><h1>Business setup</h1><p>Complete each area at your pace. Your storefront stays private until JDS readiness checks pass.</p></header>
    <div className="onboarding-progress" aria-label={`${completed.size} of ${steps.length} setup areas complete`}><span style={{width:`${completed.size/steps.length*100}%`}} /></div>
    {nextStep?<aside className="setup-next-step"><span>Recommended next step</span><strong>{nextStep.title}</strong><p>{nextStep.note}</p><Link className="primary-button" to={nextStep.to}>Continue setup</Link></aside>:<aside className="setup-next-step complete"><span>Setup complete</span><strong>Your storefront has everything required for launch.</strong><p>Review the live preview and readiness checks before sharing your link.</p><Link className="primary-button" to="/admin/design/preview">Review storefront</Link></aside>}
    <fieldset id="business" className="business-basics"><legend>Business, storefront, and pickup details</legend><label>Customer-facing business name<input value={profile.display_name} onChange={field("display_name")}/></label><label>Storefront name<input value={slug} pattern="[a-z0-9]+(?:-[a-z0-9]+)*" aria-describedby="storefront-help" onChange={(event)=>setSlug(event.target.value.toLowerCase().replace(/[^a-z0-9-]/g,""))}/><small id="storefront-help">Use lowercase letters, numbers, and hyphens. Availability is confirmed when you save.</small></label><label>Contact email<input type="email" value={profile.contact_email||""} onChange={field("contact_email")}/></label><label>Phone<input value={profile.phone||""} onChange={field("phone")}/></label><label>Timezone<select value={profile.timezone} onChange={field("timezone")}><option value="America/Toronto">Eastern time</option><option value="America/Winnipeg">Central time</option><option value="America/Edmonton">Mountain time</option><option value="America/Vancouver">Pacific time</option><option value="America/Halifax">Atlantic time</option></select></label><label>Fulfillment label<input value={profile.fulfillment_wording} onChange={field("fulfillment_wording")}/></label><label>Pickup instructions<textarea value={profile.pickup_instructions} onChange={field("pickup_instructions")}/></label></fieldset>
    <div className="onboarding-checklist">{steps.map(({key,title,note,to})=><article key={key} className={completed.has(key)?"complete":"incomplete"}><span aria-hidden="true">{completed.has(key)?"✓":"○"}</span><div><strong>{title}</strong><small>{completed.has(key)?"Complete":note}</small></div><Link to={to}>{completed.has(key)?"Review":"Set up"}</Link></article>)}</div>
    <div className="design-actions"><button className="primary-button" type="button" disabled={saving} onClick={save}>{saving?"Saving…":"Save progress"}</button></div>
    {message ? <p className="owner-page-message" aria-live="polite">{message}</p> : null}
    {state.state === "complete" && !state.publicReady ? <p className="readiness-note">Setup is complete. Ordering remains private until catalog, scheduling, and payment readiness are verified.</p> : null}
    {readiness?<section className="readiness-checks"><h2>Launch readiness</h2><ul>{Object.entries(readiness.checks).map(([key,ready])=><li key={key} className={ready?"ready":"pending"}>{ready?"Ready":"Needed"}: {key.replaceAll("_"," ")}</li>)}</ul></section>:null}
  </section>;
}
