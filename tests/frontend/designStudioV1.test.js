import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { describeLayoutCapabilities, getLayoutDefinition, layoutComparisonRows, layoutDefinitions, layoutShowsHomeQuickOrder, previewAnnouncementText, previewCatalog, previewSampleAnnouncement, previewSampleProducts } from "../../src/design/layoutDefinitions.js";

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
  assert.match(studio,/showLayoutControls=wizardStep!=="brand"/);assert.match(studio,/showCustomization=wizardStep!=="look"/);assert.match(studio,/Compare layouts/);assert.match(studio,/layoutComparisonRows\.map/);assert.match(studio,/capabilities\.quickOrder/);
  assert.doesNotMatch(studio,/createProduct|createPendingOrder|createCloverCheckout/);
  for(const id of ["modern","minimal","cozy"])assert.match(styles,new RegExp(`layout-${id}`));
});

test("merchant layout descriptions and comparison are derived from structural definitions",()=>{
  const modern=describeLayoutCapabilities("modern"),minimal=describeLayoutCapabilities("minimal"),cozy=describeLayoutCapabilities("cozy");
  assert.match(modern.hero,/Large visual hero/);assert.match(modern.quickOrder,/always on Home/);assert.match(modern.products,/Image-forward/);assert.match(modern.mobileNavigation,/Bottom mobile navigation/);
  assert.match(minimal.hero,/No large hero/);assert.match(minimal.quickOrder,/No Quick Order/);assert.match(minimal.products,/Compact menu rows/);assert.match(minimal.orderingAction,/Subtle/);
  assert.match(cozy.hero,/café-style hero/i);assert.match(cozy.quickOrder,/can be shown/);assert.match(cozy.featured,/Featured favourites/);assert.match(cozy.mobileNavigation,/Café-style mobile tabs/);
  assert.deepEqual(layoutComparisonRows.map((row)=>row.label),["Hero","Quick Order on Home","Featured content","Categories","Products","Ordering action","Cart","Mobile navigation","Overall feel"]);
  for(const row of layoutComparisonRows)assert.deepEqual(Object.keys(row.values),["modern","minimal","cozy"]);
});

test("announcement preview has immediate sample and real-content behavior without changing published fallback",()=>{
  assert.equal(previewAnnouncementText({announcement:{enabled:false,text:"Sale"}}),"");
  assert.equal(previewAnnouncementText({announcement:{enabled:true,text:""}}),previewSampleAnnouncement);
  assert.equal(previewAnnouncementText({announcement:{enabled:true,text:"Fresh muffins at noon"}}),"Fresh muffins at noon");
  assert.match(phone,/previewAnnouncementText\(config\)/);assert.match(phone,/data-preview-sample/);
  assert.match(preview,/previewAnnouncementText\(design\)/);assert.match(preview,/announcement-\$\{layout\.id\}/);
  assert.match(layout,/announcement\?\.enabled && tenant\.value\.design\.announcement\.text/);
  assert.doesNotMatch(layout,/previewSampleAnnouncement|previewAnnouncementText/);
});

test("Step 2 exposes only supported optional layout controls and immediate visual controls",()=>{
  assert.match(studio,/selectedLayout\.quickOrder==="home-cards"/);assert.match(studio,/Show Quick Order on Home/);
  assert.doesNotMatch(studio,/selectedLayout\.quickOrder!=="browse-only"/);
  assert.match(studio,/selectedLayout\.slots\.hero!=="unsupported"/);assert.match(studio,/Show announcements on my app/);assert.match(studio,/config\.announcement\?\.enabled\?<label>Announcement text/);
  for(const key of ["displayName","tagline","colors","typography","buttonStyle","logoMediaId","hero","announcement","pwa"])assert.match(studio,new RegExp(key));
  assert.match(phone,/typography-\$\{config\.typography\}/);assert.match(phone,/buttons-\$\{config\.buttonStyle\}/);assert.match(styles,/layout-phone-preview\.typography-classic/);assert.match(styles,/layout-phone-preview\.buttons-pill/);
});

test("Step 2 is grouped in merchant language without technical installed-app labels",()=>{
  for(const heading of ["Your brand","Colours &amp; style","Images","Homepage","When customers install your app"])assert.match(studio,new RegExp(heading));
  assert.match(studio,/Business or app name/);assert.match(studio,/App icon/);assert.match(studio,/Name under the icon/);assert.match(studio,/Opening screen colour/);
  assert.doesNotMatch(studio,/>Installed app appearance</);assert.doesNotMatch(studio,/>Short name</);assert.doesNotMatch(studio,/>Theme color</);assert.doesNotMatch(studio,/>Launch background</);
  assert.match(studio,/selectedLayout\.slots\.hero!=="unsupported"/);assert.match(studio,/selectedLayout\.quickOrder==="home-cards"/);
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
  assert.match(studio,/backgroundColor/);assert.match(studio,/contrast\(config\.colors\.text,config\.colors\.background\)>=4\.5/);assert.match(studio,/publishDesign/);assert.match(studio,/revertDesign/);assert.match(studio,/archiveMedia/);assert.match(studio,/logoMediaId/);assert.match(studio,/hero/);assert.match(studio,/mobileView/);assert.match(styles,/\.studio-workspace\.mobile-edit \.phone-preview-wrap\{display:none\}/);
});
