import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { layoutDefinitions, layoutShowsHeaderLogo, layoutShowsHero } from "../../src/design/layoutDefinitions.js";
import { withInstalledAppDefaults } from "../../src/design/installedAppDefaults.js";

const studio=readFileSync(new URL("../../src/admin/DesignStudioPage.jsx",import.meta.url),"utf8");
const phone=readFileSync(new URL("../../src/design/LayoutPhonePreview.jsx",import.meta.url),"utf8");
const publicLayout=readFileSync(new URL("../../src/layouts/AppLayout.jsx",import.meta.url),"utf8");
const publicHome=readFileSync(new URL("../../src/pages/HomePage.jsx",import.meta.url),"utf8");
const fullPreview=readFileSync(new URL("../../src/admin/DesignPreviewPage.jsx",import.meta.url),"utf8");
const seed=readFileSync(new URL("../../backend/app/local_review_seed.py",import.meta.url),"utf8");
const readiness=readFileSync(new URL("../../backend/app/platform/readiness.py",import.meta.url),"utf8");
const appIconComposition=readFileSync(new URL("../../src/design/AppIconComposition.jsx",import.meta.url),"utf8");
const appIconEditor=readFileSync(new URL("../../src/design/AppIconCropEditor.jsx",import.meta.url),"utf8");

test("layout definitions own optional and unsupported slot capabilities",()=>{
  assert.deepEqual(layoutDefinitions.modern.slots,{logo:"optional",hero:"optional",announcement:"optional",quickOrder:"required"});
  assert.deepEqual(layoutDefinitions.minimal.slots,{logo:"optional",hero:"unsupported",announcement:"optional",quickOrder:"unsupported"});
  assert.deepEqual(layoutDefinitions.cozy.slots,{logo:"optional",hero:"optional",announcement:"optional",quickOrder:"optional"});
  for(const layout of Object.values(layoutDefinitions))assert.equal(layoutShowsHeaderLogo(layout.id,{showLogo:false}),false);
  assert.equal(layoutShowsHero("modern",[],{showHero:false}),false);assert.equal(layoutShowsHero("modern",[],{showHero:true}),true);
  assert.equal(layoutShowsHero("cozy",[],{showHero:false}),false);assert.equal(layoutShowsHero("cozy",[],{showHero:true}),true);
  assert.equal(layoutShowsHero("minimal",["hero"],{showHero:true}),false);
});

test("legacy designs default visible while logo and hero visibility remain independent of app icon",()=>{
  const config=withInstalledAppDefaults({displayName:"Your business",colors:{primary:"#112233",background:"#ffffff"},pwa:{},logoMediaId:"logo",appIconMediaId:"icon"});
  assert.deepEqual(config.branding,{showLogo:true,showHero:true,headerMode:"logo"});
  const hidden=withInstalledAppDefaults({...config,branding:{showLogo:false,showHero:false}});
  assert.equal(hidden.logoMediaId,"logo");assert.equal(hidden.appIconMediaId,"icon");assert.deepEqual(hidden.branding,{showLogo:false,showHero:false,headerMode:"tagline"});
});

test("designer-only areas highlight active editable slots and can focus their controls",()=>{
  for(const [slot,label] of [["logo","LOGO"],["hero","HERO IMAGE"],["announcement","ANNOUNCEMENT"],["quickOrder","QUICK ORDER"]]){
    assert.match(phone,new RegExp(`${slot}:\\"${label}\\"`));
    if(!["logo"].includes(slot))assert.match(studio,new RegExp(`setActiveSlot\\(\\"${slot}\\"\\)`));
  }
  assert.match(phone,/designer\?\.activeSlot===area/);assert.match(phone,/designer\.showLayoutAreas/);assert.match(phone,/onSelectSlot/);
  assert.match(studio,/Show layout areas/);assert.match(studio,/scrollIntoView/);
});

test("optional logo and hero controls collapse their precision workflows",()=>{
  assert.match(studio,/Header branding/);assert.match(studio,/headerBrandingMode\(config\)==="logo"\?<>>?/);
  assert.match(studio,/Show hero image/);assert.match(studio,/config\.branding\.showHero\?<>>?/);
  assert.match(studio,/selectedLayout\.slots\.hero!=="unsupported"/);
  assert.match(phone,/HeaderBrandingIdentity/);assert.match(phone,/heroVisible\?<header/);
  assert.match(studio,/Use my logo/);assert.match(studio,/appIconMediaId/);
});

test("enabled empty branding slots teach their location without leaking publicly",()=>{
  assert.match(phone,/identitySlot=mode==="logo"\?"logo":"tagline"/);
  assert.match(phone,/heroEmpty\?<div className="designer-hero-empty-message"><strong>HERO IMAGE<\/strong>/);
  assert.match(phone,/heroUrl\?<PositionedSlotImage[^>]*className="layout-hero-image"/);
  assert.doesNotMatch(publicLayout,/designer-logo-empty|designer-hero-empty-message/);
  assert.doesNotMatch(publicHome,/designer-logo-empty|designer-hero-empty-message/);
  assert.doesNotMatch(fullPreview,/designer-logo-empty|designer-hero-empty-message/);
});

test("Hero composition explains Modern and Cozy without duplicate image branding",()=>{
  assert.match(phone,/A full-width image area/);
  assert.match(phone,/A warm, framed image area/);
  assert.doesNotMatch(phone,/heroUrl\?null:<h2>\{config\.displayName\}<\/h2>/);
});

test("Quick Order explains personalization and preserves each layout rule",()=>{
  assert.match(studio,/returning customers to reorder items they buy regularly/);
  assert.match(studio,/each customer’s purchase history/);
  assert.match(studio,/selectedLayout\.quickOrder==="home-cards"/);
  assert.match(studio,/describeLayoutCapabilities\(selectedLayout\)\.quickOrder/);
  assert.equal(layoutDefinitions.modern.slots.quickOrder,"required");assert.equal(layoutDefinitions.minimal.slots.quickOrder,"unsupported");assert.equal(layoutDefinitions.cozy.slots.quickOrder,"optional");
});

test("installed app has separate precision and live customer-context previews",()=>{
  assert.match(studio,/AppIconCropEditor/);assert.match(appIconComposition,/app-icon-crop-boundary/);assert.match(appIconEditor,/AppIconComposition/);
  assert.match(studio,/installed-app-customer-preview/);assert.match(studio,/What customers see/);
  assert.match(studio,/aria-label="Installed app customer preview"/);
  assert.match(studio,/mediaUrl\(config\.appIconMediaId\)/);assert.match(appIconComposition,/appIconImageStyle\(config\.imagePositions\.appIcon\)/);
  assert.match(studio,/config\.pwa\.shortName/);assert.match(studio,/Use my logo/);assert.match(studio,/Use generated brand icon/);
});

test("synthetic acquisition starts with neutral customer branding",()=>{
  assert.match(seed,/"displayName"\s*:\s*"Your business"/);
  assert.doesNotMatch(seed,/"displayName"\s*:\s*"New Merchant Demo"/);
  assert.match(phone,/config\.displayName/);assert.match(studio,/updateBusinessName/);
});

test("editor overlays cannot enter full draft preview or published storefront",()=>{
  assert.doesNotMatch(publicLayout,/designer-phone-area|data-designer-label|Show layout areas/);
  assert.doesNotMatch(publicHome,/designer-phone-area|data-designer-label|Show layout areas/);
  assert.doesNotMatch(fullPreview,/designer-phone-area|data-designer-label|Show layout areas/);
  assert.match(publicLayout,/HeaderBrandingIdentity/);assert.match(publicHome,/layoutShowsHero/);assert.match(fullPreview,/HeaderBrandingIdentity/);
});

test("readiness does not require optional logo or hero slots",()=>{
  assert.doesNotMatch(readiness,/logoMediaId|showLogo|showHero|heroMediaId/);
  assert.match(readiness,/published_design/);
});
