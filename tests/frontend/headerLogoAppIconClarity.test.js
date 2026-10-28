import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const studio=readFileSync(new URL("../../src/admin/DesignStudioPage.jsx",import.meta.url),"utf8");
const artwork=readFileSync(new URL("../../src/design/AppIconComposition.jsx",import.meta.url),"utf8");
const phone=readFileSync(new URL("../../src/design/LayoutPhonePreview.jsx",import.meta.url),"utf8");
const css=readFileSync(new URL("../../src/style.css",import.meta.url),"utf8");

test("Header Logo and App Icon use explicit, purpose-specific workflows",()=>{
  for(const label of ["Header logo","Position your header logo","Header Preview","App icon","Position your app icon","Your app icon","What customers see","Name under the icon"]){
    assert.match(studio,new RegExp(label,"i"));
  }
  assert.match(studio,/This logo appears inside the header of your ordering app/);
  assert.match(studio,/This is the icon customers see when they add your ordering app to their phone/);
  assert.match(studio,/The large image customers see near the top of your Home screen/);
});

test("Header Preview and sticky phone share the selected-layout header renderer",()=>{
  assert.match(studio,/import LayoutPhonePreview, \{ FocusedHeaderBrandingPreview \}/);
  assert.match(studio,/<FocusedHeaderBrandingPreview config=\{config\} layout=\{selectedLayout\} logoUrl=\{mediaUrl\(config\.logoMediaId\)\}/);
  assert.match(phone,/export function PreviewHeader/);assert.match(phone,/export function FocusedHeaderBrandingPreview/);
  assert.match(phone,/FocusedHeaderBrandingPreview[\s\S]*<HeaderBrandingIdentity/);
  assert.match(studio,/<LayoutPhonePreview config=\{config\}/);
});

test("Use my logo is an independent App Icon assignment in either header mode",()=>{
  assert.match(studio,/disabled=\{!config\.logoMediaId\} onClick=\{\(\)=>chooseSlot\("appIcon",config\.logoMediaId\)\}/);
  assert.doesNotMatch(studio,/disabled=\{headerBrandingMode\(config\)!==="logo"/);
  assert.match(studio,/logoMediaId:id/);assert.match(studio,/appIconMediaId:id/);
  assert.match(studio,/independent square App Icon crop/);
  assert.match(artwork,/config\.imagePositions\.appIcon/);
});

test("App Icon editing, final result, and customer context remain distinct and responsive",()=>{
  assert.match(studio,/app-icon-editor-pane/);assert.match(studio,/final-app-icon-preview/);assert.match(studio,/installed-app-customer-preview/);
  assert.match(studio,/AppIconComposition config=\{config\} src=\{mediaUrl\(config\.appIconMediaId\)\}/);
  assert.match(css,/\.app-icon-workspace\{display:grid;grid-template-columns:minmax\(0,3fr\) minmax\(240px,2fr\)/);
  assert.match(css,/@media\(max-width:760px\)\{\.app-icon-workspace\{grid-template-columns:1fr\}/);
});

test("Hero structure stays frozen while media workflow wording changes",()=>{
  assert.match(phone,/layout\.id==="modern"/);assert.match(phone,/layout\.id==="cozy"/);
  assert.match(phone,/heroContent\.cta/);assert.match(phone,/cozy-hero-action/);
  assert.doesNotMatch(phone,/config\.tagline[^\n]*hero/);
});
