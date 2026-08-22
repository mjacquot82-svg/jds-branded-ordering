import assert from "node:assert/strict";
import test from "node:test";
import { installedAppName, withInstalledAppDefaults } from "../../src/design/installedAppDefaults.js";

const base={displayName:"New Merchant Demo",colors:{primary:"#123456",background:"#f1f2f3"},pwa:{shortName:"Order",themeColor:"#6f7d5f",backgroundColor:"#f7f0e6"}};

test("installed app defaults use existing merchant branding",()=>{
  assert.equal(installedAppName("A Very Long Merchant Business Name That Needs Trimming"),"A Very Long Merchant Business ");
  assert.equal(installedAppName("  "),"Order");
  assert.deepEqual(withInstalledAppDefaults(base).pwa,{shortName:"New Merchant Demo",themeColor:"#123456",backgroundColor:"#f1f2f3"});
});

test("useful explicit installed app overrides are preserved",()=>{
  const configured={...base,pwa:{shortName:"Merchant App",themeColor:"#abcdef",backgroundColor:"#fedcba"}};
  assert.deepEqual(withInstalledAppDefaults(configured).pwa,configured.pwa);
});

test("a real business name replaces only the neutral installed-label placeholder",()=>{
  const named={...base,displayName:"Marc's Drip",pwa:{...base.pwa,shortName:"Your business"}};
  assert.equal(withInstalledAppDefaults(named).pwa.shortName,"Marc's Drip");
  assert.equal(withInstalledAppDefaults({...named,pwa:{...named.pwa,shortName:"Drip To Go"}}).pwa.shortName,"Drip To Go");
});
