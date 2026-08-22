import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { fetchBusinessProfile, fetchOnboarding, fetchReadiness, fetchStorefront, recheckReadiness, saveBusinessProfile, saveOnboarding, saveStorefront } from "../services/designStudioApi.js";
import { customizeBusinessSlug, initialBusinessDetails, merchantAppAddress, updateBusinessName } from "../setup/businessDetails.js";

export const merchantJourney = [
  { key:"look", title:"Choose your look", note:"Pick the visual style that feels like you.", to:"/admin/design" },
  { key:"brand", title:"Make it yours", note:"Add your colours, name, logo, and images.", to:"/admin/design#brand" },
  { key:"business", title:"Business details", note:"Add the information customers need.", to:"/admin/setup#business" },
  { key:"catalog", title:"Build your menu", note:"Add what customers can order.", to:"/admin/products" },
  { key:"ordering", title:"Set up ordering", note:"Choose order times, pickup times, and preparation time.", to:"/admin/scheduling" },
  { key:"payments", title:"Connect payments", note:"Connect Clover when you are ready to accept payment.", to:"/admin/setup#payments" },
  { key:"preview", title:"Preview", note:"See exactly what your customers will see.", to:"/admin/design/preview" },
  { key:"launch", title:"Launch", note:"Share your app, QR code, and printable sign.", to:"/admin/launch" },
];

const readinessCopy = {
  organization: ["Activate your business", "/admin/setup#business"],
  business_profile: ["Add your business details", "/admin/setup#business"],
  verified_hostname: ["Choose your ordering-app address", "/admin/setup#business"],
  fulfillment: ["Choose how customers can order", "/admin/scheduling"],
  hours: ["Add your business hours", "/admin/scheduling"],
  catalog: ["Add at least one menu item", "/admin/products"],
  published_design: ["Publish the design you reviewed", "/admin/design"],
  clover: ["Connect Clover before accepting payments", "/admin/setup#payments"],
};

export function journeyCompletion(stage, readiness, profile) {
  const checks = readiness?.checks || {};
  if (stage === "look") return Boolean(profile);
  if (stage === "brand") return Boolean(checks.published_design);
  if (stage === "business") return Boolean(checks.business_profile);
  if (stage === "catalog") return Boolean(checks.catalog);
  if (stage === "ordering") return Boolean(checks.hours && checks.fulfillment);
  if (stage === "payments") return Boolean(checks.clover);
  if (stage === "preview") return Boolean(readiness);
  return Boolean(readiness?.publicReady);
}

export default function OnboardingPage({ onComplete, wizard = false }) {
  const { session } = useOwnerAuth();
  const [state, setState] = useState(null); const [message, setMessage] = useState(""); const [saving, setSaving] = useState(false);
  const [profile, setProfile] = useState(null); const [readiness,setReadiness]=useState(null); const [storefront,setStorefront]=useState(null); const [slug,setSlug]=useState("");const [slugCustomized,setSlugCustomized]=useState(false);
  useEffect(() => { Promise.all([fetchOnboarding(),fetchBusinessProfile(),fetchReadiness(),fetchStorefront()]).then(([progress,business,checks,shop])=>{const details=initialBusinessDetails(business,shop);setState(progress);setProfile(details.profile);setReadiness(checks);setStorefront(shop);setSlug(details.slug);setSlugCustomized(details.slugCustomized);}).catch((error)=>setMessage(error.message)); }, []);
  if (!state || !profile) return <section className="page-section"><h1>Build your app</h1><p>{message || "Loading your progress…"}</p></section>;
  const completeCount=merchantJourney.filter(({key})=>journeyCompletion(key,readiness,profile)).length;
  const field=(key)=>(event)=>setProfile((current)=>({...current,[key]:event.target.value}));
  const nestedField=(group,key)=>(event)=>setProfile((current)=>({...current,[group]:{...(current[group]||{}),[key]:event.target.value}}));
  const businessNameField=(event)=>{const next=updateBusinessName({profile,slug,slugCustomized},event.target.value);setProfile(next.profile);setSlug(next.slug);};
  const slugField=(event)=>{const next=customizeBusinessSlug({profile,slug,slugCustomized},event.target.value);setSlug(next.slug);setSlugCustomized(true);};
  const merchantAddressSuffix=storefront.merchantAddressSuffix||"";const addressPreview=merchantAppAddress(slug,merchantAddressSuffix);
  async function save(){try{setSaving(true);await saveBusinessProfile(profile,session.csrf_token);if(slug!==storefront.slug)await saveStorefront(slug,session.csrf_token);if(!wizard)await saveOnboarding({revision:state.revision,current_step:"catalog",completed_steps:state.completedSteps},session.csrf_token);const checks=await recheckReadiness(session.csrf_token);const [next,business,shop]=await Promise.all([fetchOnboarding(),fetchBusinessProfile(),fetchStorefront()]);setState(next);setProfile(business);setReadiness(checks);setStorefront(shop);setSlug(shop.slug);setMessage("Your business details are saved. Next, let’s build your menu.");if(wizard)onComplete?.();}catch(error){setMessage(error.message);}finally{setSaving(false);}}
  return <section className={`page-section onboarding-page app-builder-setup ${wizard?"embedded-business-step":""}`}>
    {!wizard?<><header><p className="eyebrow">Your ordering app</p><h1>{session.app_launched?"Setup and readiness":"Let’s make your app ready for customers."}</h1><p>{session.app_launched?"Update any part of your app and check that everything is ready.":"Your design is taking shape. Now add the practical details your customers need."}</p></header><div className="onboarding-progress" aria-label={`${completeCount} of ${merchantJourney.length} stages ready`}><span style={{width:`${completeCount/merchantJourney.length*100}%`}} /></div><nav className="journey-cards" aria-label="Build your app stages">{merchantJourney.map((step,index)=>{const complete=journeyCompletion(step.key,readiness,profile);return <Link className={complete?"complete":""} key={step.key} to={step.to}><span>{complete?"✓":index+1}</span><div><strong>{step.title}</strong><small>{complete?"Ready to review":step.note}</small></div></Link>;})}</nav></>:null}
    <div className="setup-layout"><form id="business" className="business-details-card" onSubmit={(event)=>{event.preventDefault();save();}}><div><p className="eyebrow">Step 3</p><h2>Check your customer-facing business details</h2><p>We already have some of your business details. Check them and add anything that’s missing. Customers use these details to order and know where and how to pick up.</p></div>
      <div className="business-basics"><label>Business or app name<input required value={profile.display_name} onChange={businessNameField}/></label><label>Your app’s web address<span className="app-address-field"><input aria-describedby="app-address-result" required value={slug} minLength="3" maxLength="63" pattern="[a-z0-9]+(?:-[a-z0-9]+)*" onChange={slugField}/><span aria-hidden="true">{merchantAddressSuffix}</span></span><small id="app-address-result">{addressPreview?<>Customers will visit: <strong>{addressPreview}</strong><br/></>:null}We’ll confirm this address is available when you save.</small></label><label>Street address (optional)<input value={profile.address?.street||""} onChange={nestedField("address","street")}/></label><label>City (optional)<input value={profile.address?.city||""} onChange={nestedField("address","city")}/></label><label>Phone (optional)<input value={profile.phone||""} onChange={field("phone")}/></label><label>Customer email (optional)<input type="email" value={profile.contact_email||""} onChange={field("contact_email")}/><small>The email customers can use to contact your business.</small></label><label>Instagram page (optional)<input placeholder="https://instagram.com/yourbusiness" value={profile.socials?.instagram||""} onChange={nestedField("socials","instagram")}/></label><label>Facebook page (optional)<input placeholder="https://facebook.com/yourbusiness" value={profile.socials?.facebook||""} onChange={nestedField("socials","facebook")}/></label><label>Timezone<select required value={profile.timezone} onChange={field("timezone")}><option value="America/Toronto">Eastern time</option><option value="America/Winnipeg">Central time</option><option value="America/Edmonton">Mountain time</option><option value="America/Vancouver">Pacific time</option><option value="America/Halifax">Atlantic time</option></select></label><label>What should we call pickup?<input required value={profile.fulfillment_wording} onChange={field("fulfillment_wording")}/></label><label>Pickup instructions (optional)<textarea value={profile.pickup_instructions} placeholder="Example: Pick up at the front counter. Please have your order number ready." onChange={field("pickup_instructions")}/></label></div>
      <div className="design-actions"><button className="primary-button" disabled={saving} type="submit">{saving?"Saving…":wizard?"Save and continue":"Save and build my menu"}</button>{!wizard?<Link className="secondary-button" to="/admin/design">Back to my design</Link>:null}</div></form>
      {!wizard?<aside className="readiness-checks" id="payments"><p className="eyebrow">Your path to launch</p><h2>What’s still needed?</h2><p>These checks come from your saved app—not from boxes in your browser.</p><ul>{Object.entries(readiness.checks).map(([key,ready])=>{const [label,to]=readinessCopy[key]||[key.replaceAll("_"," "),"/admin/setup"];return <li key={key} className={ready?"ready":"pending"}><span>{ready?"✓":"○"}</span><div><strong>{label}</strong><small>{ready?"Ready":"Still needed"}</small></div>{!ready?<Link to={to}>Fix this</Link>:null}</li>;})}</ul>{readiness.checks.clover?null:<div className="payment-setup-copy"><strong>Connect Clover so customers can pay through your app.</strong><p>{globalThis.location?.hostname?.includes("localhost")||globalThis.location?.hostname?.includes("github.dev")?"Payments stay simulated during this safe review. You can continue without a real connection.":"A secure Clover connection is required before your app can accept real payments."}</p></div>}<Link className="primary-button" to={readiness.publicReady?"/admin/launch":"/admin/design/preview"}>{readiness.publicReady?"Launch my app":"Preview what customers will see"}</Link></aside>:null}
    </div>
    {message?<p className="owner-page-message" aria-live="polite">{message}</p>:null}
  </section>;
}
