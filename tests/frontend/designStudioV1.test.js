import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { getLayoutDefinition, layoutDefinitions, layoutShowsHomeQuickOrder, previewCatalog, previewSampleProducts } from "../../src/design/layoutDefinitions.js";

const studio=readFileSync(new URL("../../src/admin/DesignStudioPage.jsx",import.meta.url),"utf8");
const phone=readFileSync(new URL("../../src/design/LayoutPhonePreview.jsx",import.meta.url),"utf8");
const preview=readFileSync(new URL("../../src/admin/DesignPreviewPage.jsx",import.meta.url),"utf8");
const home=readFileSync(new URL("../../src/pages/HomePage.jsx",import.meta.url),"utf8");
const layout=readFileSync(new URL("../../src/layouts/AppLayout.jsx",import.meta.url),"utf8");
const styles=readFileSync(new URL("../../src/style.css",import.meta.url),"utf8");

test("Modern, Minimal, and Cozy declare distinct curated app structures",()=>{
  assert.deepEqual(Object.keys(layoutDefinitions),["modern","minimal","cozy"]);
  const structures=Object.values(layoutDefinitions).map((item)=>JSON.stringify({hero:item.hero,navigation:item.navigation,categories:item.categories,productCards:item.productCards,quickOrder:item.quickOrder,homeSections:item.homeSections}));
  assert.equal(new Set(structures).size,3);assert.equal(getLayoutDefinition("unknown").id,"cozy");
  assert.equal(layoutShowsHomeQuickOrder("modern",[]),true);assert.equal(layoutShowsHomeQuickOrder("minimal",["quickOrder"]),false);assert.equal(layoutShowsHomeQuickOrder("cozy",["quickOrder"]),true);assert.equal(layoutShowsHomeQuickOrder("cozy",[]),false);
});

test("layout cards select a draft while branding and commerce remain separate",()=>{
  assert.match(studio,/Choose your app layout/);assert.match(studio,/layoutChoices\.map/);assert.match(studio,/selectLayout\(item\.id\)/);assert.match(studio,/saveDesignDraft\(\{revision:draft\.revision,config:nextConfig\}/);assert.match(studio,/Your layout choice saves automatically/);
  assert.doesNotMatch(studio,/createProduct|createPendingOrder|createCloverCheckout/);
  for(const id of ["modern","minimal","cozy"])assert.match(styles,new RegExp(`layout-${id}`));
});

test("layout phone preview uses samples only until real menu content exists",()=>{
  const empty=previewCatalog([],[]);assert.equal(empty.sample,true);assert.equal(empty.products,previewSampleProducts);
  const real=[{id:"real",name:"Merchant Latte",published:true}];const owned=previewCatalog([{id:"coffee"}],real);assert.equal(owned.sample,false);assert.equal(owned.products[0],real[0]);assert.ok(!owned.products.some((item)=>item.id.startsWith("sample-")));
  assert.match(phone,/Sample menu for layout preview/);assert.match(phone,/modern-mobile-dock/);assert.match(phone,/minimal-footer/);assert.match(phone,/cozy-mobile-tabs/);assert.doesNotMatch(phone,/createProduct|addProduct|createPendingOrder/);
});

test("shared storefront applies published layout structure without separate commerce apps",()=>{
  assert.match(layout,/getLayoutDefinition/);assert.match(layout,/navigation-\$\{storefrontLayout\.navigation\}/);assert.match(home,/layoutShowsHero/);assert.match(home,/layoutShowsHomeQuickOrder/);assert.match(home,/showHomeQuickOrder/);assert.match(preview,/layout\.homeSections\.map\(renderSection\)/);assert.match(preview,/Preview only — customers can’t order here/);assert.doesNotMatch(preview,/createCloverCheckout|createPendingOrder|Add to cart/);
});

test("Design Studio preserves branding, versioning, media, contrast, and mobile review",()=>{
  assert.match(studio,/backgroundColor/);assert.match(studio,/4\.5:1 contrast/);assert.match(studio,/publishDesign/);assert.match(studio,/revertDesign/);assert.match(studio,/archiveMedia/);assert.match(studio,/logoMediaId/);assert.match(studio,/hero/);assert.match(studio,/mobileView/);assert.match(styles,/\.studio-workspace\.mobile-edit \.phone-preview-wrap\{display:none\}/);
});
