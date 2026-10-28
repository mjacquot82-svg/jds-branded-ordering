import assert from "node:assert/strict";
import { after, test } from "node:test";
import { JSDOM } from "jsdom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const vite=await createServer({appType:"custom",server:{hmr:false,middlewareMode:true}});
const {default:LayoutPhonePreview}=await vite.ssrLoadModule("/src/design/LayoutPhonePreview.jsx");
after(()=>vite.close());

const base={template:"cozy",displayName:"Ladel's",tagline:"Fresh coffee. Good mornings.",typography:"classic",buttonStyle:"rounded",colors:{primary:"#6f7d5f",accent:"#b98564",background:"#f7f0e6",surface:"#ffffff",text:"#2f3328"},branding:{showLogo:true,showHero:true,headerMode:"logo"},heroContent:"image",sections:["hero","categories","quickOrder"],announcement:{enabled:false,text:""},imagePositions:{logo:{x:50,y:50,zoom:1},hero:{x:35,y:65,zoom:1.2},appIcon:{x:50,y:50,zoom:1}}};

test("Hero and Logo assignments render immediately and survive unrelated rerenders",async()=>{
  const dom=new JSDOM('<div id="root"></div>',{url:"https://review.test/setup/brand"});const previous={window:globalThis.window,document:globalThis.document,navigator:globalThis.navigator};globalThis.window=dom.window;globalThis.document=dom.window.document;Object.defineProperty(globalThis,"navigator",{configurable:true,value:dom.window.navigator});
  const root=createRoot(dom.window.document.querySelector("#root"));const render=async(config=base,heroUrl=null,logoUrl=null)=>act(async()=>root.render(React.createElement(LayoutPhonePreview,{config,heroUrl,logoUrl,designer:{activeSlot:"hero"}})));
  try{
    await render();assert.equal(dom.window.document.querySelector(".layout-hero-image"),null);
    await render(base,"/media/hero.png");const hero=dom.window.document.querySelector(".layout-hero-image");assert.equal(hero?.getAttribute("src"),"/media/hero.png");assert.equal(hero?.dataset.imageLoadState,"loading");Object.defineProperties(hero,{naturalWidth:{value:1717},naturalHeight:{value:916}});hero.getBoundingClientRect=()=>({width:390,height:195});await act(async()=>hero.dispatchEvent(new dom.window.Event("load",{bubbles:false})));assert.equal(hero.dataset.imageLoadState,"loaded");assert.equal(hero.dataset.naturalSize,"1717x916");assert.equal(hero.dataset.renderedSize,"390x195");
    for(const position of [{x:35,y:20,zoom:1.2},{x:80,y:20,zoom:1.2},{x:80,y:20,zoom:2},{x:50,y:50,zoom:1},{x:10,y:90,zoom:2.5}]){await render({...base,imagePositions:{...base.imagePositions,hero:position}},"/media/hero.png");const changed=dom.window.document.querySelector(".layout-hero-image");assert.equal(changed?.getAttribute("src"),"/media/hero.png");assert.equal(changed?.style.objectPosition,`${position.x}% ${position.y}%`);assert.equal(changed?.style.transform,`scale(${position.zoom})`);}
    await render({...base,tagline:"Changed but unrelated"},"/media/hero.png");assert.ok(dom.window.document.querySelector(".layout-hero-image"));
    await render({...base,colors:{...base.colors,primary:"#334455"},announcement:{enabled:true,text:"Today only"}},"/media/hero.png","/media/logo.png");assert.equal(dom.window.document.querySelector(".header-branding-identity img")?.getAttribute("src"),"/media/logo.png");
    await render({...base,branding:{...base.branding,headerMode:"tagline",showLogo:false}},"/media/hero.png","/media/logo.png");assert.match(dom.window.document.querySelector(".header-branding-identity")?.textContent||"",/Fresh coffee/);assert.ok(dom.window.document.querySelector(".layout-hero-image"));
    await render(base,"/media/hero.png","/media/logo.png");assert.equal(dom.window.document.querySelector(".header-branding-identity img")?.getAttribute("src"),"/media/logo.png");
  }finally{await act(async()=>root.unmount());dom.window.close();globalThis.window=previous.window;globalThis.document=previous.document;Object.defineProperty(globalThis,"navigator",{configurable:true,value:previous.navigator});}
});
