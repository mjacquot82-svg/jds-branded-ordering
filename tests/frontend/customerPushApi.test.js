import assert from "node:assert/strict";
import test from "node:test";
import { pushSubscriptionPayload, revokeCurrentPushSubscription, savePushSubscription, setLunchPreference, vapidKey } from "../../src/services/customerPushApi.js";

test("vapidKey decodes an unpadded URL-safe application server key", () => {
  globalThis.atob ||= (value) => Buffer.from(value, "base64").toString("binary");
  const raw=Uint8Array.from([4,...Array.from({length:64},(_,index)=>index)]);
  const encoded=Buffer.from(raw).toString("base64url");
  assert.deepEqual(vapidKey(encoded),raw);
});

const response=(status,payload={})=>({ok:status>=200&&status<300,status,json:async()=>payload});

test("subscription persistence uses authenticated CSRF mutation without customer identity",async()=>{
  let request;
  const subscription={endpoint:"https://push.example/device",keys:{p256dh:"key",auth:"auth"}};
  await savePushSubscription(subscription,"csrf",{apiBaseUrl:"https://api.example",fetchImpl:async(...args)=>{request=args;return response(201,{id:"device-id"})}});
  assert.equal(request[0],"https://api.example/api/v1/customer/push/subscriptions");
  assert.equal(request[1].credentials,"include");
  assert.equal(request[1].headers["X-CSRF-Token"],"csrf");
  assert.deepEqual(JSON.parse(request[1].body),subscription);
  assert.equal("customer_user_id" in JSON.parse(request[1].body),false);
});

test("Android PushSubscription serialization is allowlisted to the strict backend schema",async()=>{
  const browserSubscription={toJSON:()=>({endpoint:"https://push.example/android",expirationTime:null,keys:{p256dh:"p256dh-value",auth:"auth-value"},futureBrowserField:"ignored"})};
  const payload=pushSubscriptionPayload(browserSubscription,"Android");
  assert.deepEqual(payload,{endpoint:"https://push.example/android",keys:{p256dh:"p256dh-value",auth:"auth-value"},content_encoding:"aes128gcm",device_label:"Android"});
  assert.equal("expirationTime" in payload,false);
  assert.equal("futureBrowserField" in payload,false);
  let request;
  const saved=await savePushSubscription(payload,"csrf",{apiBaseUrl:"https://api.example",fetchImpl:async(...args)=>{request=args;return response(201,{id:"android-device"})}});
  assert.deepEqual(saved,{id:"android-device"});
  assert.deepEqual(Object.keys(JSON.parse(request[1].body)).sort(),["content_encoding","device_label","endpoint","keys"]);
});

test("browser subscriptions without expirationTime remain compatible",()=>{
  const payload=pushSubscriptionPayload({toJSON:()=>({endpoint:"https://push.example/browser",keys:{p256dh:"p256dh-value",auth:"auth-value"}})},"Browser");
  assert.equal(payload.endpoint,"https://push.example/browser");
  assert.equal("expirationTime" in payload,false);
});

test("incomplete browser subscription data fails before an HTTP request",async()=>{
  assert.throws(()=>pushSubscriptionPayload({toJSON:()=>({endpoint:"https://push.example/incomplete",keys:{auth:"auth-value"}})},"Android"),/subscription is incomplete/);
});

test("FastAPI validation arrays produce a safe customer-facing message",async()=>{
  await assert.rejects(()=>savePushSubscription({endpoint:"bad"},"csrf",{fetchImpl:async()=>response(422,{detail:[{loc:["body","endpoint"],msg:"sensitive input rejected",input:"do-not-display"}]})}),/Notification details were rejected\. Please try again\./);
});

test("current-device revocation identifies the browser endpoint and account preference is separate",async()=>{
  const requests=[];const fetchImpl=async(...args)=>{requests.push(args);return response(args[1].method==="POST"?204:200,{lunch_special_enabled:false})};
  await revokeCurrentPushSubscription("https://push.example/device","csrf",{fetchImpl});
  await setLunchPreference(false,"csrf",{fetchImpl});
  assert.deepEqual(JSON.parse(requests[0][1].body),{endpoint:"https://push.example/device"});
  assert.deepEqual(JSON.parse(requests[1][1].body),{lunch_special_enabled:false});
});
