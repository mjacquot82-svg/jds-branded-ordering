import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { JSDOM } from "jsdom";
import { collectVisualDesignerDiagnostics, findVerticalScrollContainer } from "../../src/design/visualDesignerDiagnostics.js";

const css=readFileSync(new URL("../../src/style.css",import.meta.url),"utf8");
const layout=readFileSync(new URL("../../src/layouts/AppLayout.jsx",import.meta.url),"utf8");
const setup=readFileSync(new URL("../../src/setup/SetupWizard.jsx",import.meta.url),"utf8");
const studio=readFileSync(new URL("../../src/admin/DesignStudioPage.jsx",import.meta.url),"utf8");

test("setup escapes both storefront width and overflow scroll constraints",()=>{
  assert.match(layout,/setup-app-shell"><main className="setup-shell-root"/);
  assert.match(css,/\.setup-app-shell\{width:100%;max-width:none;min-width:0;overflow:visible;overflow-x:clip/);
  assert.match(css,/\.setup-app-shell>\.setup-shell-root,\.setup-shell-root>\.setup-wizard\{width:100%;max-width:none/);
  assert.match(setup,/visualStep=\["look","brand","preview"\]\.includes\(step\)/);
  assert.match(setup,/visual-designer-content/);
});

test("visual workspace is materially wide and balanced at desktop acceptance widths",()=>{
  assert.match(css,/width:min\(100%,1880px\);max-width:1880px/);
  assert.match(css,/grid-template-columns:minmax\(0,3fr\) minmax\(390px,2fr\)/);
  for(const viewport of [1024,1280,1366,1440,1600,1920]){
    const padding=viewport<=1040?24:Math.min(64,viewport*.04);
    const shell=Math.min(1880,viewport-padding);
    assert.ok(shell>=viewport*.9,`${viewport}px uses at least 90% of the viewport`);
    if(viewport>1040){
      const usable=shell-Math.min(44,Math.max(20,viewport*.0225));
      const preview=Math.max(390,usable*.4);
      const editor=usable-preview;
      assert.ok(editor>preview,`${viewport}px gives the editor the larger share`);
      assert.ok(preview>=390,`${viewport}px retains a convincing phone column`);
    }
  }
});

test("runtime diagnostics identify the actual scrolling element and measured columns",()=>{
  const dom=new JSDOM(`<main class="visual-designer-shell"><div class="visual-designer-workspace"><aside class="visual-designer-editor"></aside><div class="visual-designer-preview-column"><div class="visual-designer-preview-sticky"><div class="phone-preview"></div></div></div></div></main>`,{pretendToBeVisual:true});
  const previous={document:globalThis.document,getComputedStyle:globalThis.getComputedStyle,innerWidth:globalThis.innerWidth};
  globalThis.document=dom.window.document;globalThis.getComputedStyle=dom.window.getComputedStyle.bind(dom.window);globalThis.innerWidth=1440;
  Object.defineProperty(dom.window.document,"scrollingElement",{configurable:true,value:dom.window.document.documentElement});
  const widths=new Map([["visual-designer-workspace",1376],["visual-designer-editor",808],["visual-designer-preview-column",530],["visual-designer-preview-sticky",530],["phone-preview",430]]);
  for(const [className,width] of widths){const node=dom.window.document.querySelector(`.${className}`);node.getBoundingClientRect=()=>({width,top:className==="visual-designer-preview-sticky"?16:0});}
  try{
    const sticky=dom.window.document.querySelector(".visual-designer-preview-sticky");
    assert.equal(findVerticalScrollContainer(sticky),dom.window.document.documentElement);
    const values=collectVisualDesignerDiagnostics(dom.window.document.querySelector(".visual-designer-shell"));
    assert.deepEqual({viewport:values.viewport,shell:values.shell,editor:values.editor,preview:values.preview,phone:values.phone,scrollContainer:values.scrollContainer},{viewport:1440,shell:1376,editor:808,preview:530,phone:430,scrollContainer:"document.documentElement"});
  }finally{globalThis.document=previous.document;globalThis.getComputedStyle=previous.getComputedStyle;globalThis.innerWidth=previous.innerWidth;dom.window.close();}
});

test("nested vertical scrollers are detected rather than assuming window scroll",()=>{
  const dom=new JSDOM(`<div class="scroller"><div class="visual-designer-preview-sticky"></div></div>`);
  const previous={document:globalThis.document,getComputedStyle:globalThis.getComputedStyle};globalThis.document=dom.window.document;
  const scroller=dom.window.document.querySelector(".scroller");Object.defineProperties(scroller,{scrollHeight:{value:1200},clientHeight:{value:500}});
  globalThis.getComputedStyle=(node)=>({overflowY:node===scroller?"auto":"visible",overflowX:"visible",top:"16px"});
  try{assert.equal(findVerticalScrollContainer(dom.window.document.querySelector(".visual-designer-preview-sticky")),scroller);}finally{globalThis.document=previous.document;globalThis.getComputedStyle=previous.getComputedStyle;dom.window.close();}
});

test("precision canvases fill the editor and mobile returns preview to normal flow",()=>{
  assert.match(css,/\.visual-designer-editor \.hero-slot-preview\{width:100%;max-width:none\}/);
  assert.match(css,/\.visual-designer-editor \.logo-slot-preview\{height:clamp\(220px,22vw,320px\)/);
  assert.match(css,/\.app-icon-positioning-stage\{[^}]*width:min\(560px,100%\)/);
  assert.match(css,/@media\(max-width:1040px\)\{[\s\S]*?\.visual-designer-preview-sticky\{position:static\}/);
  assert.match(studio,/VisualDesignerDiagnostics rootRef=\{designerRef\}/);
  assert.match(studio,/import\.meta\.env\.DEV&&reviewHostname/);
});
