import { useEffect, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import DesignStudioPage from "../admin/DesignStudioPage.jsx";
import DesignPreviewPage from "../admin/DesignPreviewPage.jsx";
import LaunchPage from "../admin/LaunchPage.jsx";
import OnboardingPage from "../admin/OnboardingPage.jsx";
import ProductsPage from "../admin/ProductsPage.jsx";
import SchedulingPage from "../admin/SchedulingPage.jsx";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { fetchOnboarding, fetchReadiness, saveOnboarding } from "../services/designStudioApi.js";
import { getCloverConnectUrl } from "../services/cloverService.js";

export const setupSteps = ["welcome","look","brand","business","catalog","ordering","payments","preview","launch"];
const labels = { welcome:"Welcome", look:"Choose your app layout", brand:"Make it yours", business:"Business details", catalog:"Build your menu", ordering:"Set up ordering", payments:"Connect payments", preview:"Preview", launch:"Launch" };

function PaymentSetupStep() {
  const [readiness,setReadiness]=useState(null);
  useEffect(()=>{fetchReadiness().then(setReadiness);},[]);
  if(!readiness)return <section className="wizard-focus-card"><h1>Connect payments</h1><p>Checking payment readiness…</p></section>;
  const simulated=readiness.reviewMode === "local" || readiness.reviewMode === "staging";
  return <section className="wizard-focus-card payment-wizard-step"><p className="eyebrow">Step 6</p><h1>Let customers pay through your app.</h1><p>Connect Clover so customer payments flow securely through the system you already use.</p>{simulated?<div className="wizard-simulation-note"><strong>Payment connection is simulated in this review environment.</strong><p>No real Clover request or transaction can be made here.</p></div>:readiness.checks.clover?<div className="wizard-success-note"><strong>Clover is connected.</strong><p>Your payment connection is ready for launch.</p></div>:<a className="primary-button" href={getCloverConnectUrl()}>Connect Clover</a>}</section>;
}

export default function SetupWizard() {
  const { step = "welcome" } = useParams();
  const navigate=useNavigate();
  const { businesses,businessStatus,logout,selectBusiness,session }=useOwnerAuth();
  const [progress,setProgress]=useState(null); const [message,setMessage]=useState(""); const [busy,setBusy]=useState(false);
  const [readiness,setReadiness]=useState(null);
  const [catalogDirty,setCatalogDirty]=useState(false);
  useEffect(()=>{fetchOnboarding().then(setProgress).catch((error)=>setMessage(error.message));},[step]);
  useEffect(()=>{if(step==="catalog")fetchReadiness().then(setReadiness).catch((error)=>setMessage(error.message));},[step]);
  if(!setupSteps.includes(step))return <Navigate replace to="/setup/welcome"/>;
  const index=setupSteps.indexOf(step);
  const visualStep=["look","brand","preview"].includes(step);
  async function checkpoint(next){if(!progress)return;setBusy(true);setMessage("");try{const saved=await saveOnboarding({revision:progress.revision,current_step:next,completed_steps:progress.completedSteps},session.csrf_token);setProgress(saved);navigate(`/setup/${next}`);}catch(error){setMessage(error.message);}finally{setBusy(false);}}
  async function saveAndExit(){if(!progress)return;setBusy(true);try{await saveOnboarding({revision:progress.revision,current_step:step,completed_steps:progress.completedSteps},session.csrf_token);await logout();navigate("/owner/login",{replace:true});}catch(error){setMessage(error.message);setBusy(false);}}
  if(step==="welcome")return <main className="setup-wizard welcome-wizard"><header className="wizard-brand">JDS <span>Branded Ordering</span></header><section className="wizard-welcome-card"><p className="eyebrow">Welcome</p><h1>Let’s build your ordering app.</h1><p>We’ll help you choose a design, add your business information, set up your menu and ordering, connect payments, and get ready to launch.</p><button className="primary-button" disabled={!progress||busy} type="button" onClick={()=>checkpoint("look")}>Get started</button></section>{message?<p role="alert">{message}</p>:null}</main>;
  return <main className={`setup-wizard wizard-step-${step} ${visualStep?"visual-setup-step":"focused-setup-step"}`}><header className="wizard-topbar"><div className="wizard-brand">JDS <span>Branded Ordering</span></div><div className="wizard-business">{businessStatus==="loading"?<span>Loading business…</span>:businesses.length>1?<label><span className="sr-only">Current business</span><select value={businesses.find((item)=>item.organization_id===session.organization_id)?.membership_id||""} onChange={(event)=>selectBusiness(event.target.value)}>{businesses.map((item)=><option key={item.membership_id} value={item.membership_id}>{item.organization_name}</option>)}</select></label>:null}<button className="text-button" disabled={busy} type="button" onClick={saveAndExit}>Save &amp; exit</button></div></header><section className="wizard-progress-shell"><div><span>Step {index} of 8</span><strong>{labels[step]}</strong></div><ol>{setupSteps.slice(1).map((item,itemIndex)=><li className={itemIndex+1<index?"complete":item===step?"current":""} key={item}><span>{itemIndex+1}</span><small>{labels[item]}</small></li>)}</ol></section><div className={`wizard-content ${visualStep?"visual-designer-content":"focused-setup-content"}`}>
    {step==="look"?<DesignStudioPage guided wizardStep="look" onContinue={()=>checkpoint("brand")}/>:null}
    {step==="brand"?<DesignStudioPage guided wizardStep="brand" onContinue={()=>checkpoint("business")}/>:null}
    {step==="business"?<OnboardingPage wizard onComplete={()=>checkpoint("catalog")}/>:null}
    {step==="catalog"?<ProductsPage setupMode onCatalogChange={()=>fetchReadiness().then(setReadiness).catch((error)=>setMessage(error.message))} onDirtyChange={setCatalogDirty}/>:null}
    {step==="ordering"?<SchedulingPage setupMode/>:null}
    {step==="payments"?<PaymentSetupStep/>:null}
    {step==="preview"?<DesignPreviewPage setupMode/>:null}
    {step==="launch"?<LaunchPage setupMode/>:null}
  </div>{step!=="launch"?<footer className="wizard-actions"><button className="secondary-button" disabled={busy||(step==="catalog"&&catalogDirty)} type="button" onClick={()=>checkpoint(setupSteps[index-1])}>Back</button>{!["look","brand","business"].includes(step)?<div className="wizard-continue-action">{step==="catalog"&&catalogDirty?<small>Save or cancel your product changes before leaving this step.</small>:step==="catalog"&&!readiness?.checks?.catalog?<small>Create a visible category and add at least one available product customers can order.</small>:null}<button className="primary-button" disabled={busy||(step==="catalog"&&(catalogDirty||!readiness?.checks?.catalog))} type="button" onClick={()=>checkpoint(setupSteps[index+1])}>{step==="preview"?"Continue to launch":"Continue"}</button></div>:null}</footer>:null}{message?<p className="wizard-message" role="alert">{message}</p>:null}</main>;
}
