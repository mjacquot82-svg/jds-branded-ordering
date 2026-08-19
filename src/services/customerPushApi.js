const BASE="/api/v1/customer/push";
const root=()=> (import.meta.env?.VITE_API_BASE_URL||"").replace(/\/+$/,"");
async function call(path,{method="GET",body,csrfToken,fetchImpl=globalThis.fetch,apiBaseUrl=root()}={}) {
  const response=await fetchImpl(`${apiBaseUrl.replace(/\/+$/,"")}${BASE}${path}`,{method,credentials:"include",headers:{Accept:"application/json",...(body?{"Content-Type":"application/json"}:{}),...(csrfToken?{"X-CSRF-Token":csrfToken}:{})},body:body?JSON.stringify(body):undefined});
  if(!response.ok){let data={};try{data=await response.json()}catch{};throw new Error(data?.detail?.message||(Array.isArray(data?.detail)?"Notification details were rejected. Please try again.":"Notifications could not be updated."))}
  return response.status===204?null:response.json();
}
export const fetchPushConfig=(options={})=>call("/config",options);
export const fetchPushStatus=(options={})=>call("/status",options);
export const savePushSubscription=(subscription,csrfToken,options={})=>call("/subscriptions",{...options,method:"POST",csrfToken,body:subscription});
export const revokeCurrentPushSubscription=(endpoint,csrfToken,options={})=>call("/subscriptions/revoke-current",{...options,method:"POST",csrfToken,body:{endpoint}});
export const removePushSubscription=(id,csrfToken,options={})=>call(`/subscriptions/${id}`,{...options,method:"DELETE",csrfToken});
export const setLunchPreference=(enabled,csrfToken,options={})=>call("/preferences",{...options,method:"PUT",csrfToken,body:{lunch_special_enabled:enabled}});

export function pushSubscriptionPayload(subscription,deviceLabel){
  const serialized=subscription?.toJSON?.();
  if(typeof serialized?.endpoint!=="string"||typeof serialized?.keys?.p256dh!=="string"||typeof serialized?.keys?.auth!=="string")throw new Error("Browser notification subscription is incomplete.");
  return {endpoint:serialized.endpoint,keys:{p256dh:serialized.keys.p256dh,auth:serialized.keys.auth},content_encoding:"aes128gcm",device_label:deviceLabel};
}

export function vapidKey(value){const pad="=".repeat((4-value.length%4)%4);const raw=atob((value+pad).replace(/-/g,"+").replace(/_/g,"/"));return Uint8Array.from(raw,c=>c.charCodeAt(0))}
export function pushSupport(){
  const supported="serviceWorker" in navigator&&"PushManager" in window&&"Notification" in window;
  const ios=/iPad|iPhone|iPod/.test(navigator.userAgent)||(navigator.platform==="MacIntel"&&navigator.maxTouchPoints>1); const installed=window.matchMedia?.("(display-mode: standalone)").matches||navigator.standalone===true;
  const version=navigator.userAgent.match(/OS (\d+)[_.](\d+)/); const modernIos=!version||Number(`${version[1]}.${version[2]}`)>=16.4;
  return {supported,needsInstall:ios&&modernIos&&!installed,permission:supported?Notification.permission:"unsupported"};
}
