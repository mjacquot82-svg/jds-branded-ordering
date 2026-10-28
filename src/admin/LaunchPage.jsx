import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { fetchEntitlements, fetchLaunchKit, fetchOnboarding, fetchReadiness, fetchStorefront, launchMerchant } from "../services/designStudioApi.js";

const checkNames = {
  organization: "Business is active",
  business_profile: "Business details",
  verified_hostname: "Storefront address",
  fulfillment: "Online ordering enabled",
  hours: "Weekly hours",
  catalog: "Published menu",
  published_design: "Published design",
  payment_connected: "Payment connection",
  clover: "Payment connection",
};
const checkActions = {
  business_profile: ["Add your business details", "/admin/setup#business"],
  verified_hostname: ["Choose your ordering-app address", "/admin/setup#business"],
  fulfillment: ["Choose when customers can order", "/admin/scheduling"],
  hours: ["Add your business hours", "/admin/scheduling"],
  catalog: ["Add at least one menu item", "/admin/products"],
  published_design: ["Review and publish your design", "/admin/design/preview"],
  payment_connected: ["Connect payments before accepting orders", "/admin/setup#payments"],
  clover: ["Connect payments before accepting orders", "/admin/setup#payments"],
};
const subscriptionMessages = {
  unconfigured: "Billing is not enabled in this environment. All V1 features remain available.",
  trialing: "Your trial is active.",
  active: "Your subscription is active.",
  grace: "Your subscription needs attention, but features remain available during the grace period.",
  past_due: "Your subscription payment needs attention. Premium features are paused.",
  cancelled: "Your subscription is cancelled. Your business data is retained.",
  inactive: "Your subscription is inactive. Your business data is retained.",
  none: "No subscription is assigned yet.",
};

export default function LaunchPage({ setupMode = false }) {
  const { refreshSession, session } = useOwnerAuth();
  const navigate=useNavigate();
  const [state,setState]=useState({status:"loading"});
  async function load(){try{const [readiness,storefront,entitlements,onboarding]=await Promise.all([fetchReadiness(),fetchStorefront(),fetchEntitlements(),fetchOnboarding()]);let kit=null;if(onboarding.initialSetupCompletedAt)kit=await fetchLaunchKit();setState({status:"ready",readiness,storefront,entitlements,onboarding,kit});}catch(error){setState({status:"error",error:error.message});}}
  useEffect(()=>{load();},[]);
  if(state.status==="loading")return <section className="page-section launch-page"><h1>Preparing your launch area…</h1><p>Checking your storefront and launch assets.</p></section>;
  if(state.status==="error")return <section className="page-section launch-page"><h1>Launch area unavailable</h1><p role="alert">{state.error}</p><button className="secondary-button" type="button" onClick={()=>globalThis.location?.reload?.()}>Try again</button></section>;
  const {readiness,storefront,entitlements,onboarding,kit}=state;
  const launched=Boolean(onboarding.initialSetupCompletedAt);
  const paymentOk=Boolean(readiness.checks.payment_connected ?? readiness.checks.clover); const commerceReady=["business_profile","verified_hostname","fulfillment","hours","catalog"].every((key)=>readiness.checks[key]) && paymentOk;
  const wizardActions={business_profile:"/setup/business",verified_hostname:"/setup/business",fulfillment:"/setup/ordering",hours:"/setup/ordering",catalog:"/setup/catalog",published_design:"/setup/preview",payment_connected:"/setup/payments",clover:"/setup/payments"};
  const firstMissing=Object.keys(readiness.checks).find((key)=>!readiness.checks[key]);
  async function launch(){if(!globalThis.confirm?.("Launch the ordering app you reviewed?"))return;try{setState({...state,status:"publishing"});await launchMerchant(session.csrf_token);await load();}catch(error){setState({...state,status:"ready",error:error.message});}}
  async function enterApplication(){await refreshSession();navigate("/admin",{replace:true});}
  return <section className={`page-section launch-page ${setupMode?"embedded-launch-step":""}`}><header><p className="eyebrow">{launched&&setupMode?"You’re live!":"Your final step"}</p><h1>{launched?setupMode?"You created your ordering app.":"Your ordering app is ready.":"Let’s get your app ready to launch."}</h1><p>{launched&&setupMode?"Share it with customers, open your storefront, or enter your owner dashboard.":"Everything here is checked against your saved app. Your storefront stays private until every launch check passes."}</p></header>
    {state.error?<p className="owner-page-message error" role="alert">{state.error}</p>:null}<div className="launch-grid"><section className="operations-panel"><h2>{launched?"Here’s what your customers can use":"A few things still need attention"}</h2><ul className="launch-checks">{Object.entries(readiness.checks).map(([key,ready])=>{const [label,adminTo]=checkActions[key]||[checkNames[key]||key.replaceAll("_"," "),"/admin/setup"];const to=setupMode?(wizardActions[key]||"/setup/business"):adminTo;return <li className={ready?"ready":"pending"} key={key}><span aria-hidden="true">{ready?"✓":"○"}</span><span><strong>{label}</strong><small>{ready?"Ready":"Still needed"}</small></span>{!ready&&key!=="published_design"?<Link to={to}>Fix this</Link>:null}</li>;})}</ul>{!launched&&commerceReady?<button className="primary-button" type="button" onClick={launch}>Launch my app</button>:!launched?<Link className="primary-button" to={setupMode?(wizardActions[firstMissing]||"/setup/business"):"/admin/setup"}>Continue building my app</Link>:null}</section>
      <section className="operations-panel launch-assets"><h2>Customer launch kit</h2>{kit?<><label>Storefront URL<input readOnly value={kit.url}/></label><img src={kit.qrUrl} alt={`QR code for ${storefront.slug}`}/><div className="design-actions"><a className="primary-button" href={kit.url} target="_blank" rel="noreferrer">Open my app</a><a className="secondary-button" href={kit.printUrl} target="_blank" rel="noreferrer">Open printable sign</a><a className="secondary-button" href={kit.qrUrl} download={`${storefront.slug}-qr.svg`}>Download QR code</a>{setupMode?<button className="primary-button" type="button" onClick={enterApplication}>Go to dashboard</button>:null}</div><p>Place the sign near your counter or entrance so customers can scan and order from their phones.</p></>:<div className="preview-empty"><h3>Launch assets unlock when ready</h3><p>Complete the checks shown here, then return to download your QR code and printable sign.</p></div>}</section>
    </div><section className="operations-panel subscription-summary"><h2>Plan and feature access</h2><strong>{(entitlements.plan||"V1 access").replaceAll("-"," ")}</strong><p>{subscriptionMessages[entitlements.state]||`Subscription status: ${entitlements.state.replaceAll("_"," ")}.`}</p><ul>{Object.entries(entitlements.features).filter(([,enabled])=>enabled).map(([feature])=><li key={feature}>{feature.replace(/([A-Z])/g," $1").replace(/^./,(letter)=>letter.toUpperCase())}</li>)}</ul></section>
  </section>;
}
