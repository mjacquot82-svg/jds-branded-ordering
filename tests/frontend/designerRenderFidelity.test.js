import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { appIconCroppedPixelGeometry, appIconImageStyle, appIconPixelGeometry, createMediaUrlIndex, headerBrandingMode, heroContentVisibility, imagePositionContracts, resolveAssignedMediaUrl, slotImageStyle } from "../../src/design/imageSlotRendering.js";
import { layoutDefinitions } from "../../src/design/layoutDefinitions.js";

const files=["src/admin/DesignStudioPage.jsx","src/design/LayoutPhonePreview.jsx","src/admin/DesignPreviewPage.jsx","src/pages/HomePage.jsx","src/layouts/AppLayout.jsx"].map((path)=>readFileSync(new URL(`../../${path}`,import.meta.url),"utf8"));
const [studio,phone,full,home,layout]=files;
const header=readFileSync(new URL("../../src/design/HeaderBrandingIdentity.jsx",import.meta.url),"utf8");
const css=readFileSync(new URL("../../src/style.css",import.meta.url),"utf8");

test("editor positioning ranges match the slot-specific save contract",()=>{
  assert.deepEqual(imagePositionContracts.logo,{minX:0,maxX:100,minY:0,maxY:100,minZoom:1,maxZoom:3});
  assert.deepEqual(imagePositionContracts.hero,{minX:0,maxX:100,minY:0,maxY:100,minZoom:1,maxZoom:3});
  assert.deepEqual(imagePositionContracts.appIcon,{minX:0,maxX:100,minY:0,maxY:100,minZoom:.4,maxZoom:3});
  assert.match(studio,/min=\{imagePositionContracts\[slot\]\.minZoom\}/);
});

test("one canonical image style owns position zoom and fit",()=>{
  assert.deepEqual(slotImageStyle({x:17,y:82,zoom:1.35}),{objectFit:"cover",objectPosition:"17% 82%",transform:"scale(1.35)",transformOrigin:"center"});
  assert.deepEqual(slotImageStyle({x:40,y:60,zoom:2},"contain"),{objectFit:"contain",objectPosition:"40% 60%",transform:"scale(2)",transformOrigin:"center"});
  for(const source of [studio,phone,full,home])assert.match(source,/PositionedSlotImage/);
  assert.match(layout,/HeaderBrandingIdentity/);
});

test("phone full preview and storefront share canonical hero geometry",()=>{
  assert.equal(layoutDefinitions.modern.heroSlot.aspectRatio,16/9);assert.equal(layoutDefinitions.cozy.heroSlot.aspectRatio,2);assert.equal(layoutDefinitions.minimal.heroSlot,null);
  for(const source of [studio,phone,full,home])assert.match(source,/heroSlot\.aspectRatio/);
  for(const source of [phone,full,home])assert.match(source,/PositionedSlotImage[^>]*className="layout-hero-image"/);
});

test("logo precision and customer surfaces use layout slot geometry",()=>{
  for(const value of Object.values(layoutDefinitions))assert.ok(value.logoSlot.aspectRatio>0);
  assert.match(studio,/selectedLayout\.logoSlot\.aspectRatio/);assert.match(header,/layout\.logoSlot\.aspectRatio/);
  assert.match(full,/HeaderBrandingIdentity/);assert.match(layout,/HeaderBrandingIdentity/);
});

test("Hero Content keeps Tagline in the header and offers clean image or CTA",()=>{
  assert.deepEqual(heroContentVisibility("image"),{tagline:false,cta:false});
  assert.deepEqual(heroContentVisibility("cta"),{tagline:false,cta:true});
  for(const value of ["image","cta"])assert.match(studio,new RegExp(`value="${value}"`));
  assert.doesNotMatch(studio,/value="tagline"|value="tagline-cta"/);
  assert.match(studio,/Your Tagline stays in the header/);
  assert.doesNotMatch(phone,/heroUrl\?null:<h2>/);assert.doesNotMatch(home,/tenant\.design\.displayName<\/strong>/);
});

test("Header Branding preserves both identities and uses one shared renderer",()=>{
  assert.equal(headerBrandingMode({branding:{headerMode:"logo"}}),"logo");assert.equal(headerBrandingMode({branding:{headerMode:"tagline"}}),"tagline");
  assert.match(studio,/name="headerBranding"/);assert.match(studio,/setHeaderMode\("logo"\)/);assert.match(studio,/setHeaderMode\("tagline"\)/);
  for(const source of [phone,full,layout])assert.match(source,/HeaderBrandingIdentity/);
  assert.match(header,/designer-logo-empty">Your logo/);assert.match(header,/designer-tagline-empty">Your tagline/);
});

test("media assignment resolves immediately without an unrelated draft update",()=>{
  const asset={id:42,ownerUrl:"/hero/42"};const index=createMediaUrlIndex([asset]);
  assert.equal(resolveAssignedMediaUrl(index,"42"),"/hero/42");assert.equal(resolveAssignedMediaUrl(index,null),null);
  assert.match(studio,/useMemo\(\(\)=>createMediaUrlIndex\(media\),\[media\]\)/);assert.match(studio,/resolveAssignedMediaUrl\(mediaById,id\)/);
});

test("editor guidance stays out of full and public rendering",()=>{
  assert.match(phone,/HERO CONTENT|TAGLINE|BUSINESS NAME/);
  for(const source of [full,home,layout])assert.doesNotMatch(source,/designer-phone-area|data-designer-label|designer-hero-empty-message/);
});

test("loaded Hero pixels outrank fallback while guidance stays non-opaque",()=>{
  assert.match(css,/\.layout-hero>\.layout-hero-image[^}]*z-index:1[^}]*opacity:1[^}]*visibility:visible/);
  assert.match(css,/\.layout-hero:has\(\.layout-hero-image\)::before[^}]*z-index:2[^}]*pointer-events:none/);
  assert.match(css,/\.layout-phone-preview \.layout-hero\.designer-phone-area::after\{z-index:12\}/);
  assert.doesNotMatch(css,/\.layout-phone-preview \.layout-hero\.designer-phone-area::after\{[^}]*background/);
  assert.match(css,/\.layout-phone-preview\.layout-cozy \.hero-framed-photo\{min-height:0;aspect-ratio:2\/1\}/);
  assert.match(css,/\.layout-phone-preview\.layout-modern \.hero-immersive\{min-height:0;aspect-ratio:16\/9\}/);
});

test("canonical app icon transform mirrors output positioning math",()=>{
  assert.deepEqual(appIconImageStyle({x:25,y:75,zoom:2}),{objectFit:"cover",objectPosition:"25% 75%",position:"absolute",inset:0,width:"100%",height:"100%",transform:"scale(2)",transformOrigin:"25% 75%"});
  const normalized=[500,100,50].map((size)=>{const value=appIconPixelGeometry({x:25,y:75,zoom:1.4},1800,600,size);return Object.fromEntries(Object.entries(value).map(([key,item])=>[key,Number((item/size).toFixed(8))]));});
  assert.deepEqual(normalized[0],normalized[1]);assert.deepEqual(normalized[1],normalized[2]);
  const cropped=[512,192].map((size)=>{const value=appIconCroppedPixelGeometry({x:25,y:75,zoom:1.4},1800,600,size);return Object.fromEntries(Object.entries(value).map(([key,item])=>[key,Number((item/size).toFixed(8))]));});assert.deepEqual(cropped[0],cropped[1]);
});
