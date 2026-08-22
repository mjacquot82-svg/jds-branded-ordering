import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { imageRequirementForSlot, imageRequirements, validateImageForSlot } from "../../src/design/imageRequirements.js";
import { layoutDefinitions } from "../../src/design/layoutDefinitions.js";

const studio=readFileSync(new URL("../../src/admin/DesignStudioPage.jsx",import.meta.url),"utf8");
const phone=readFileSync(new URL("../../src/design/LayoutPhonePreview.jsx",import.meta.url),"utf8");
const home=readFileSync(new URL("../../src/pages/HomePage.jsx",import.meta.url),"utf8");
const css=readFileSync(new URL("../../src/style.css",import.meta.url),"utf8");
const appIconEditor=readFileSync(new URL("../../src/design/AppIconCropEditor.jsx",import.meta.url),"utf8");

test("layouts declare distinct supported image slots and guidance",()=>{
  assert.deepEqual(layoutDefinitions.modern.imageSlots,["logo","modernHero","appIcon"]);
  assert.deepEqual(layoutDefinitions.minimal.imageSlots,["logo","appIcon"]);
  assert.deepEqual(layoutDefinitions.cozy.imageSlots,["logo","cozyHero","appIcon"]);
  assert.equal(imageRequirementForSlot("minimal","hero"),null);
  assert.equal(imageRequirementForSlot("modern","hero").ratio,16/9);
  assert.equal(imageRequirementForSlot("cozy","hero").ratio,2);
  assert.equal(imageRequirements.product.minWidth,800);
});

test("image validation rejects unsafe files and warns about poor fit",()=>{
  const unsupported=validateImageForSlot({type:"image/gif",size:100,width:512,height:512},imageRequirements.appIcon);
  assert.match(unsupported.errors[0],/PNG, JPEG, or WebP/);
  const large=validateImageForSlot({type:"image/png",size:10_000_001,width:512,height:512},imageRequirements.appIcon);
  assert.match(large.errors[0],/larger than 10 MB/);
  const low=validateImageForSlot({type:"image/png",size:100,width:128,height:128},imageRequirements.appIcon);
  assert.match(low.warnings[0],/may look blurry/);
  const wide=validateImageForSlot({type:"image/png",size:100,width:2000,height:300},imageRequirements.appIcon);
  assert.ok(wide.warnings.some((item)=>/square image/i.test(item)));
});

test("logo hero and app icon have purpose-specific assignment and positioning",()=>{
  assert.match(studio,/Upload header logo/);assert.match(studio,/Upload hero image/);assert.match(studio,/Upload app icon/);assert.match(studio,/Use my logo/);
  assert.match(studio,/logoMediaId:id/);assert.match(studio,/hero:\{mode:id\?"image":"color",mediaId:id\}/);assert.match(studio,/appIconMediaId:id/);
  assert.match(studio,/imagePositions:\{\.\.\.config\.imagePositions/);assert.match(studio,/original image is never changed/);
  assert.match(studio,/selectedLayout\.slots\.hero!=="unsupported"/);assert.match(studio,/generated fallback/);
});

test("slot changes update previews immediately without authoritative samples",()=>{
  assert.match(phone,/HeaderBrandingIdentity/);assert.match(phone,/config\.imagePositions\?\.hero/);assert.match(phone,/layout-hero-image/);
  assert.match(home,/tenant\.design\?\.imagePositions\?\.hero/);assert.match(studio,/mediaUrl\(config\.appIconMediaId\)/);
  assert.doesNotMatch(studio,/createProduct|createPendingOrder/);
});

test("assigned images expose large slot-accurate positioning editors",()=>{
  assert.match(studio,/hero-slot-preview hero-slot-\$\{selectedLayout\.id\}/);
  assert.match(css,/\.hero-slot-preview\{[^}]*aspect-ratio:16\/9/);
  assert.match(css,/\.hero-slot-cozy\{aspect-ratio:2\/1/);
  assert.match(studio,/selectedLayout\.slots\.hero!=="unsupported"/);
  assert.match(studio,/aria-label="Header Logo final crop preview"/);
  assert.match(appIconEditor,/aria-label="App Icon positioning editor"/);
  assert.match(css,/\.app-icon-positioning-stage\{[^}]*aspect-ratio:1/);
  assert.match(css,/\.app-icon-crop-boundary\{[^}]*inset:15%/);
});

test("precision editors and phone preview share the same crop state",()=>{
  assert.match(studio,/config\.imagePositions\[slot\]\.x/);
  assert.match(studio,/updatePosition\(slot,\{x:Number\(event\.target\.value\)\}\)/);
  assert.match(studio,/updatePosition\(slot,\{y:Number\(event\.target\.value\)\}\)/);
  assert.match(studio,/updatePosition\(slot,\{zoom:Number\(event\.target\.value\)\}\)/);
  assert.match(studio,/LayoutPhonePreview config=\{config\}/);
});
