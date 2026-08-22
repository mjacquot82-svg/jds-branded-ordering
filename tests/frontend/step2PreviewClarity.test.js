import assert from "node:assert/strict";
import { after, test } from "node:test";
import { JSDOM } from "jsdom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const vite=await createServer({appType:"custom",server:{hmr:false,middlewareMode:true}});
const {default:LayoutPhonePreview,FocusedHeaderBrandingPreview}=await vite.ssrLoadModule("/src/design/LayoutPhonePreview.jsx");
const {default:AppIconArtwork}=await vite.ssrLoadModule("/src/design/AppIconArtwork.jsx");
const {default:AppIconCropEditor}=await vite.ssrLoadModule("/src/design/AppIconCropEditor.jsx");
const {getLayoutDefinition}=await vite.ssrLoadModule("/src/design/layoutDefinitions.js");
after(()=>vite.close());

const config={template:"cozy",displayName:"Marc's Drip",tagline:"i drip it you drink it",typography:"classic",buttonStyle:"rounded",colors:{primary:"#6f7d5f",accent:"#b98564",background:"#f7f0e6",surface:"#fff",text:"#2f3328"},branding:{showLogo:false,showHero:true,headerMode:"tagline"},heroContent:"image",sections:["hero","categories","quickOrder"],announcement:{enabled:false,text:""},imagePositions:{logo:{x:50,y:50,zoom:1},hero:{x:50,y:50,zoom:1},appIcon:{x:23,y:77,zoom:1.8}},pwa:{shortName:"Marc's Drip"}};

test("Step 2 layout-area guidance excludes structural-only regions",async()=>{
  const dom=new JSDOM('<div id="root"></div>');const old={window:globalThis.window,document:globalThis.document,navigator:globalThis.navigator};globalThis.window=dom.window;globalThis.document=dom.window.document;Object.defineProperty(globalThis,"navigator",{configurable:true,value:dom.window.navigator});const root=createRoot(dom.window.document.querySelector("#root"));
  try{await act(async()=>root.render(React.createElement(LayoutPhonePreview,{config,heroUrl:"/hero.png",designer:{showLayoutAreas:true}})));const labels=[...dom.window.document.querySelectorAll("[data-designer-label]")].map((node)=>node.dataset.designerLabel);assert.ok(labels.includes("TAGLINE"));assert.ok(labels.includes("HERO IMAGE"));assert.ok(labels.includes("QUICK ORDER"));for(const unrelated of ["CATEGORIES","FEATURED","NAVIGATION"])assert.ok(!labels.includes(unrelated));}
  finally{await act(async()=>root.unmount());dom.window.close();globalThis.window=old.window;globalThis.document=old.document;Object.defineProperty(globalThis,"navigator",{configurable:true,value:old.navigator});}
});

test("focused Header Preview contains only the shared branding slot",async()=>{
  const dom=new JSDOM('<div id="root"></div>');const old={window:globalThis.window,document:globalThis.document,navigator:globalThis.navigator};globalThis.window=dom.window;globalThis.document=dom.window.document;Object.defineProperty(globalThis,"navigator",{configurable:true,value:dom.window.navigator});const root=createRoot(dom.window.document.querySelector("#root"));
  try{await act(async()=>root.render(React.createElement(FocusedHeaderBrandingPreview,{config,layout:getLayoutDefinition("cozy"),designer:{activeSlot:"tagline"}})));assert.match(dom.window.document.body.textContent,/i drip it you drink it/);assert.doesNotMatch(dom.window.document.body.textContent,/Welcome|Bag/);assert.ok(dom.window.document.querySelector(".header-branding-identity.mode-tagline"));}
  finally{await act(async()=>root.unmount());dom.window.close();globalThis.window=old.window;globalThis.document=old.document;Object.defineProperty(globalThis,"navigator",{configurable:true,value:old.navigator});}
});

test("Position, Your App Icon, and customer context share one canonical crop",async()=>{
  const dom=new JSDOM('<div id="root"></div>');const old={window:globalThis.window,document:globalThis.document,navigator:globalThis.navigator};globalThis.window=dom.window;globalThis.document=dom.window.document;Object.defineProperty(globalThis,"navigator",{configurable:true,value:dom.window.navigator});const root=createRoot(dom.window.document.querySelector("#root"));
  try{await act(async()=>root.render(React.createElement("div",null,React.createElement(AppIconArtwork,{config,src:"/icon.png",className:"position",editor:true}),React.createElement(AppIconArtwork,{config,src:"/icon.png",className:"result"}),React.createElement(AppIconArtwork,{config,src:"/icon.png",className:"customer"}))));const styles=[...dom.window.document.querySelectorAll(".installed-app-icon img")].map((node)=>node.getAttribute("style"));assert.equal(new Set(styles).size,1);assert.equal(dom.window.document.querySelectorAll('.app-icon-crop-boundary').length,1);}
  finally{await act(async()=>root.unmount());dom.window.close();globalThis.window=old.window;globalThis.document=old.document;Object.defineProperty(globalThis,"navigator",{configurable:true,value:old.navigator});}
});

test("final crop and result remain identical through every positioning control",async()=>{
  const dom=new JSDOM('<div id="root"></div>');const old={window:globalThis.window,document:globalThis.document,navigator:globalThis.navigator};globalThis.window=dom.window;globalThis.document=dom.window.document;Object.defineProperty(globalThis,"navigator",{configurable:true,value:dom.window.navigator});const root=createRoot(dom.window.document.querySelector("#root"));
  try{for(const position of [{x:10,y:50,zoom:1},{x:90,y:15,zoom:1.4},{x:35,y:85,zoom:2.2},{x:50,y:50,zoom:.7},{x:50,y:50,zoom:1}]){const next={...config,imagePositions:{...config.imagePositions,appIcon:position}};await act(async()=>root.render(React.createElement("div",null,React.createElement(AppIconCropEditor,{config:next,src:"/logo.png"}),React.createElement("div",{className:"your-icon"},React.createElement(AppIconArtwork,{config:next,src:"/logo.png"})),React.createElement("div",{className:"customer-icon"},React.createElement(AppIconArtwork,{config:next,src:"/logo.png"})) )));const crop=dom.window.document.querySelector(".app-icon-editor-composition img")?.getAttribute("style");assert.equal(dom.window.document.querySelector(".your-icon img")?.getAttribute("style"),crop);assert.equal(dom.window.document.querySelector(".customer-icon img")?.getAttribute("style"),crop);assert.equal(dom.window.document.querySelector(".your-icon .app-icon-source-canvas")?.className,dom.window.document.querySelector(".customer-icon .app-icon-source-canvas")?.className);}assert.equal(dom.window.document.querySelectorAll(".app-icon-crop-boundary").length,1);assert.match(dom.window.document.querySelector(".app-icon-crop-boundary")?.textContent||"",/Icon crop/i);assert.equal(dom.window.document.querySelector(".app-icon-safe-area"),null);}
  finally{await act(async()=>root.unmount());dom.window.close();globalThis.window=old.window;globalThis.document=old.document;Object.defineProperty(globalThis,"navigator",{configurable:true,value:old.navigator});}
});
