import assert from "node:assert/strict";
import test from "node:test";
import { installedAppName, resetToLayoutColors, withInstalledAppDefaults } from "../../src/design/installedAppDefaults.js";
import { layoutDefinitions } from "../../src/design/layoutDefinitions.js";

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

test("colour reset uses each layout palette and preserves unrelated design state",()=>{
  const configured={...base,displayName:"Marc's Drip",tagline:"Still here",template:"cozy",colors:{primary:"#111111",accent:"#222222",background:"#333333",surface:"#444444",text:"#555555"},pwa:{shortName:"Drip",themeColor:"#111111",backgroundColor:"#333333"},branding:{headerMode:"tagline"},hero:{mediaId:"hero"},appIconMediaId:"icon",imagePositions:{appIcon:{x:12,y:34,zoom:.7}},typography:"classic",buttonStyle:"pill",announcement:{enabled:true,text:"Hello"},sections:["hero","quickOrder"]};
  for(const layout of Object.values(layoutDefinitions)){
    const reset=resetToLayoutColors({...configured,template:layout.id},layout);
    assert.deepEqual(reset.colors,layout.defaultColors);assert.equal(reset.pwa.themeColor,layout.defaultColors.primary);assert.equal(reset.pwa.backgroundColor,layout.defaultColors.background);
    for(const key of ["displayName","tagline","branding","hero","appIconMediaId","imagePositions","typography","buttonStyle","announcement","sections"])assert.deepEqual(reset[key],configured[key]);
  }
});

test("explicit installed-app colour overrides survive layout colour reset",()=>{
  const config={...base,colors:{primary:"#111111",accent:"#222222",background:"#333333",surface:"#444444",text:"#555555"},pwa:{...base.pwa,themeColor:"#abcdef",backgroundColor:"#fedcba"}};
  const reset=resetToLayoutColors(config,layoutDefinitions.modern);assert.equal(reset.pwa.themeColor,"#abcdef");assert.equal(reset.pwa.backgroundColor,"#fedcba");
});
