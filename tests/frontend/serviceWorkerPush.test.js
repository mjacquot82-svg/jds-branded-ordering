import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import vm from "node:vm";

function workerHarness(){
  const listeners={};const shown=[];const opened=[];
  const context={URL,self:{location:{origin:"https://ladels.example"},addEventListener:(name,handler)=>{listeners[name]=handler},registration:{showNotification:async(...args)=>shown.push(args)}},clients:{matchAll:async()=>[],openWindow:async(url)=>opened.push(url)}};
  vm.runInNewContext(readFileSync(new URL("../../public/service-worker.js",import.meta.url),"utf8"),context);
  return {listeners,shown,opened};
}

test("push worker has no fetch interception and rejects malformed payloads",async()=>{
  const harness=workerHarness();assert.equal(harness.listeners.fetch,undefined);
  harness.listeners.push({data:{json:()=>({version:99,title:"Bad",body:"Bad"})},waitUntil:()=>assert.fail("Malformed push must not schedule a notification")});
  harness.listeners.push({data:{json:()=>({version:1,title:"T".repeat(81),body:"Bad"})},waitUntil:()=>assert.fail("Oversized push must not schedule a notification")});
  harness.listeners.push({data:{json:()=>({version:1,title:"Okay",body:"B".repeat(281)})},waitUntil:()=>assert.fail("Oversized push must not schedule a notification")});
  assert.equal(harness.shown.length,0);
});

test("customer consent clearly covers Lunch Special and occasional café updates",()=>{
  const settings=readFileSync(new URL("../../src/components/NotificationSettings.jsx",import.meta.url),"utf8");
  assert.match(settings,/Café notifications/);
  assert.match(settings,/Get today’s Lunch Special and occasional updates from The Guest House\./);
});

test("push worker replaces external destinations and opens only same-origin routes",async()=>{
  const harness=workerHarness();let pending;
  harness.listeners.push({data:{json:()=>({version:1,title:"Lunch",body:"Today",destination:"https://evil.example/phish",announcementId:"a"})},waitUntil:value=>{pending=value}});
  await pending;assert.equal(harness.shown[0][1].data.destination,"https://ladels.example/");
  let clicked;let closed=false;
  harness.listeners.notificationclick({notification:{data:harness.shown[0][1].data,close:()=>{closed=true}},waitUntil:value=>{clicked=value}});
  await clicked;assert.equal(closed,true);assert.deepEqual(harness.opened,["https://ladels.example/"]);
});

test("push worker preserves an encoded product query on the allowlisted menu route",async()=>{
  const harness=workerHarness();let pending;
  harness.listeners.push({data:{json:()=>({version:1,title:"Lunch",body:"Today",destination:"/menu?product=chef%27s%20bowl%2F%C3%A9t%C3%A9",announcementId:"lunch"})},waitUntil:value=>{pending=value}});
  await pending;
  assert.equal(harness.shown[0][1].data.destination,"https://ladels.example/menu?product=chef%27s%20bowl%2F%C3%A9t%C3%A9");
  let clicked;
  harness.listeners.notificationclick({notification:{data:harness.shown[0][1].data,close:()=>{}},waitUntil:value=>{clicked=value}});
  await clicked;
  assert.deepEqual(harness.opened,["https://ladels.example/menu?product=chef%27s%20bowl%2F%C3%A9t%C3%A9"]);
});
