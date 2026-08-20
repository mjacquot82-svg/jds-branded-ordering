import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchEntitlements, fetchLaunchKit, fetchReadiness, fetchStorefront } from "../services/designStudioApi.js";

const checkNames = {
  organization: "Business is active",
  business_profile: "Business details",
  verified_hostname: "Storefront address",
  fulfillment: "Online ordering enabled",
  hours: "Weekly hours",
  catalog: "Published menu",
  published_design: "Published design",
  clover: "Clover connection",
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

export default function LaunchPage() {
  const [state,setState]=useState({status:"loading"});
  useEffect(()=>{Promise.all([fetchReadiness(),fetchStorefront(),fetchEntitlements()]).then(async([readiness,storefront,entitlements])=>{let kit=null;if(readiness.publicReady){kit=await fetchLaunchKit();}setState({status:"ready",readiness,storefront,entitlements,kit});}).catch((error)=>setState({status:"error",error:error.message}));},[]);
  if(state.status==="loading")return <section className="page-section launch-page"><h1>Preparing your launch area…</h1><p>Checking your storefront and launch assets.</p></section>;
  if(state.status==="error")return <section className="page-section launch-page"><h1>Launch area unavailable</h1><p role="alert">{state.error}</p><button className="secondary-button" type="button" onClick={()=>globalThis.location?.reload?.()}>Try again</button></section>;
  const {readiness,storefront,entitlements,kit}=state;
  return <section className="page-section launch-page"><header><p className="eyebrow">Share your storefront</p><h1>Launch</h1><p>Your storefront stays private until every server-verified launch check is complete.</p></header>
    <div className="launch-grid"><section className="operations-panel"><h2>{readiness.publicReady?"Ready to share":"Finish setup before sharing"}</h2><ul className="launch-checks">{Object.entries(readiness.checks).map(([key,ready])=><li className={ready?"ready":"pending"} key={key}><span aria-hidden="true">{ready?"✓":"○"}</span><span><strong>{checkNames[key]||key.replaceAll("_"," ")}</strong><small>{ready?"Ready":"Still needed"}</small></span></li>)}</ul>{!readiness.publicReady?<Link className="primary-button" to="/admin/setup">Continue setup</Link>:null}</section>
      <section className="operations-panel launch-assets"><h2>Customer launch kit</h2>{kit?<><label>Storefront URL<input readOnly value={kit.url}/></label><img src={kit.qrUrl} alt={`QR code for ${storefront.slug}`}/><div className="design-actions"><a className="primary-button" href={kit.printUrl} target="_blank" rel="noreferrer">Open printable sign</a><a className="secondary-button" href={kit.qrUrl} download={`${storefront.slug}-qr.svg`}>Download QR code</a></div><p>Place the sign near your counter or entrance so customers can scan and order from their phones.</p></>:<div className="preview-empty"><h3>Launch assets unlock when ready</h3><p>Complete the checks shown here, then return to download your QR code and printable sign.</p></div>}</section>
    </div><section className="operations-panel subscription-summary"><h2>Plan and feature access</h2><strong>{(entitlements.plan||"V1 access").replaceAll("-"," ")}</strong><p>{subscriptionMessages[entitlements.state]||`Subscription status: ${entitlements.state.replaceAll("_"," ")}.`}</p><ul>{Object.entries(entitlements.features).filter(([,enabled])=>enabled).map(([feature])=><li key={feature}>{feature.replace(/([A-Z])/g," $1").replace(/^./,(letter)=>letter.toUpperCase())}</li>)}</ul></section>
  </section>;
}
