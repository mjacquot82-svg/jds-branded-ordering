import {useEffect,useState} from "react";
import {Bell, BellOff} from "lucide-react";
import {fetchPushConfig,fetchPushStatus,pushSubscriptionPayload,pushSupport,revokeCurrentPushSubscription,savePushSubscription,setLunchPreference,vapidKey} from "../services/customerPushApi.js";

export default function NotificationSettings({csrfToken}){
 const [state,setState]=useState({loading:true,config:null,status:null,error:"",busy:false,currentDevice:false}); const support=pushSupport();
 const load=()=>Promise.all([fetchPushConfig(),fetchPushStatus(),support.supported?navigator.serviceWorker.ready.then(r=>r.pushManager.getSubscription()).catch(()=>null):null]).then(([config,status,local])=>setState(s=>({...s,loading:false,config,status,currentDevice:Boolean(local),error:""}))).catch(e=>setState(s=>({...s,loading:false,error:e.message})));
 useEffect(()=>{load()},[]);
 async function enable(){setState(s=>({...s,busy:true,error:""}));let subscription;let saved;
  try{if(Notification.permission!=="granted"&&await Notification.requestPermission()!=="granted")throw new Error("Notifications weren’t allowed in this browser.");
   const registration=await navigator.serviceWorker.ready; subscription=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:vapidKey(state.config.vapid_public_key)});
   saved=await savePushSubscription(pushSubscriptionPayload(subscription,navigator.userAgentData?.platform||navigator.platform||"This device"),csrfToken); localStorage.setItem("ladelsPushSubscriptionId",saved.id);
   await setLunchPreference(true,csrfToken); await load();
  }catch(e){try{if(saved)await revokeCurrentPushSubscription(subscription.endpoint,csrfToken);await subscription?.unsubscribe();localStorage.removeItem("ladelsPushSubscriptionId")}catch{};setState(s=>({...s,error:e.message}))}finally{setState(s=>({...s,busy:false}))}}
 async function disableAccount(){setState(s=>({...s,busy:true,error:""}));try{await setLunchPreference(false,csrfToken);await load()}catch(e){setState(s=>({...s,error:e.message}))}finally{setState(s=>({...s,busy:false}))}}
 async function disableDevice(){setState(s=>({...s,busy:true,error:""}));try{const reg=await navigator.serviceWorker.ready;const local=await reg.pushManager.getSubscription();if(local){await revokeCurrentPushSubscription(local.endpoint,csrfToken);await local.unsubscribe()}localStorage.removeItem("ladelsPushSubscriptionId");await load()}catch(e){setState(s=>({...s,error:e.message}))}finally{setState(s=>({...s,busy:false}))}}
 if(state.loading)return <section id="notifications" className="content-block"><p>Loading notification settings…</p></section>;
 const enabled=state.status?.lunch_special_enabled; const unavailable=!state.config?.enrollment_enabled;
 return <section id="notifications" className="content-block notification-settings"><div className="account-card"><span className="account-avatar"><Bell size={24}/></span><div><h2>Café notifications</h2><p>Get today’s Lunch Special and occasional updates from The Guest House.</p></div></div>
  {state.error?<p className="form-status" role="alert">{state.error}</p>:null}
  {unavailable?<p>Café notifications are not available yet.</p>:support.needsInstall?<p>On iPhone or iPad, add Ladel’s to your Home Screen, then open it there to enable notifications.</p>:!support.supported?<p>This browser doesn’t support café notifications.</p>:support.permission==="denied"?<p>Notifications are blocked in your browser settings. You can allow them there and return to this page.</p>:<>
   <div className="notification-state"><strong>{enabled?"Café notifications are on":"Café notifications are off"}</strong><span>{state.currentDevice?"This device is enabled":"This device is not enabled"} · {state.status.active_device_count} active {state.status.active_device_count===1?"device":"devices"}</span></div>
   {(!enabled||!state.currentDevice)?<button className="primary-button" disabled={state.busy} onClick={enable} type="button"><Bell size={17}/> {state.busy?"Enabling…":enabled?"Enable on this device":"Enable café notifications"}</button>:null}
   {enabled?<button className="secondary-button" disabled={state.busy} onClick={disableAccount} type="button"><BellOff size={17}/> Turn off for my account</button>:null}
   {state.currentDevice?<button className="text-button" disabled={state.busy} onClick={disableDevice} type="button">Disable this device</button>:null}
  </>}</section>;
}
