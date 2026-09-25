import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchDesignPreview, fetchReadiness } from "../services/designStudioApi.js";
import { fetchDemoStatus } from "../services/demoFunnelApi.js";
import { useCatalogProducts } from "../stores/catalogStore.js";
import { getLayoutDefinition, layoutShowsHero, layoutShowsHomeQuickOrder, previewAnnouncementText } from "../design/layoutDefinitions.js";
import PositionedSlotImage from "../design/PositionedSlotImage.jsx";
import HeaderBrandingIdentity from "../design/HeaderBrandingIdentity.jsx";
import { heroContentVisibility } from "../design/imageSlotRendering.js";
import ProductImage from "../components/ProductImage.jsx";
import { starterPreviewUrl, withOwnerProductImage } from "../services/starterMedia.js";

const previewActions = {
  business_profile:["Add your business details.","/setup/business"],
  verified_hostname:["Choose your ordering-app address.","/setup/business"],
  fulfillment:["Choose how customers can order.","/setup/ordering"],
  hours:["Add your business hours.","/setup/ordering"],
  catalog:["Add at least one menu item.","/setup/catalog"],
  clover:["Finish connecting payments.","/setup/payments"],
  payment_connected:["Finish connecting payments.","/setup/payments"],
  organization:["Activate your store with JDS.","/setup/launch"],
};
// Readiness items a free-demo prospect cannot complete until JDS activates the store.
const ACTIVATION_ONLY_CHECKS = new Set(["organization","verified_hostname","fulfillment","payment_connected","clover"]);

// Free demos without their own hero photo get an intentional starter hero instead of an empty colour block:
// business name, tagline, JDS illustrated placeholders, and a readable "ordering opens after activation" note.
export const DEMO_HERO_STARTERS = Object.freeze(["starter:cafe-restaurant/latte@1", "starter:cafe-restaurant/plain-croissant@1", "starter:cafe-restaurant/muffin@1"]);
export function showDemoHero({ isProspect = false, hasHeroImage = false } = {}) {
  return isProspect === true && !hasHeroImage;
}

export function previewMissingChecks(checks = {}, isProspect = false) {
  return Object.entries(checks).filter(([key,ready])=>!ready&&key!=="published_design"&&!(key==="clover"&&"payment_connected" in checks)&&!(isProspect&&ACTIVATION_ONLY_CHECKS.has(key))).map(([key])=>key);
}

export default function DesignPreviewPage({ setupMode = false }) {
  const [preview,setPreview]=useState(null);const [error,setError]=useState("");
  const [readiness,setReadiness]=useState(null);
  const [demo,setDemo]=useState(null);
  useEffect(()=>{fetchDemoStatus().then(setDemo).catch(()=>setDemo(null));},[]);
  const {categories,products:catalogProducts,loading,error:catalogError}=useCatalogProducts();
  const products=useMemo(()=>catalogProducts.map(withOwnerProductImage),[catalogProducts]);
  useEffect(()=>{Promise.all([fetchDesignPreview(),fetchReadiness()]).then(([nextPreview,nextReadiness])=>{setPreview(nextPreview);setReadiness(nextReadiness);}).catch((reason)=>setError(reason.message));},[]);
  const assets=useMemo(()=>new Map((preview?.media||[]).map((asset)=>[asset.id,asset])),[preview]);
  if(error)return <section className="page-section"><h1>App preview unavailable</h1><p role="alert">{error}</p><Link to="/admin/design">Return to Design Studio</Link></section>;
  if(!preview||loading)return <section className="page-section"><h1>Preparing your app preview…</h1><p>Loading your latest design and menu.</p></section>;
  const design=preview.design;const hero=assets.get(design.hero?.mediaId);const logo=assets.get(design.logoMediaId);const layout=getLayoutDefinition(design.template);const announcementText=previewAnnouncementText(design);const heroPosition=design.imagePositions?.hero||{x:50,y:50,zoom:1};const heroContent=heroContentVisibility(design.heroContent);
  const menuSection=(heading)=> <section className="preview-catalog-section"><h2>{heading}</h2>{catalogError?<p role="alert">Catalog preview unavailable: {catalogError.message}</p>:products.length?categories.map((category)=>{const items=products.filter((product)=>product.category===category.id&&product.published);return items.length?<section key={category.id}><h3>{category.name}</h3><div className={`preview-products presentation-${design.productCardPresentation}`}>{items.map((product)=><article key={product.backendId}><ProductImage src={product.image} alt={`${product.name} product photo`} loading="eager"/><strong>{product.name}</strong><p>{product.description}</p><span>${Number(product.price).toFixed(2)}</span></article>)}</div></section>:null;}):<div className="preview-empty"><h3>Your menu will appear here</h3><p>Add and publish products before launch.</p></div>}</section>;
  const isProspect=demo?.isProspect===true;const demoHero=showDemoHero({isProspect,hasHeroImage:Boolean(hero)});
  const renderSection=(section)=>({
    hero:layoutShowsHero(design.template,design.sections,design.branding)?(demoHero?<section className={`full-hero-composition full-hero-${layout.id} demo-hero-composition`} key="hero"><header className="demo-hero"><div className="demo-hero-copy"><p className="demo-hero-name">{design.displayName}</p><h1>{design.tagline||"Fresh coffee and baking, ready when you are."}</h1>{heroContent.cta?<div className="demo-hero-cta"><button disabled type="button">{layout.id==="cozy"?"Explore the menu":"Start an order"}</button><small>Ordering opens after activation</small></div>:null}</div><div className="demo-hero-art" aria-hidden="true">{DEMO_HERO_STARTERS.map((reference)=><img alt="" decoding="async" key={reference} loading="eager" src={starterPreviewUrl(reference)}/>)}</div><p className="demo-hero-note">Starter hero · add your own photo under Design → Hero image</p></header></section>:<section className={`full-hero-composition full-hero-${layout.id}`} key="hero"><header className={heroContent.cta&&layout.id==="modern"?"has-hero-content":""} style={{aspectRatio:layout.heroSlot.aspectRatio}}>{hero?<PositionedSlotImage className="layout-hero-image" src={hero.url} position={heroPosition}/>:null}{heroContent.cta&&layout.id==="modern"?<button disabled type="button">Start an order</button>:null}</header>{heroContent.cta&&layout.id==="cozy"?<button disabled type="button">Explore the menu</button>:null}</section>):null,
    announcement:announcementText?<p key="announcement" className={`preview-announcement announcement-${layout.id}`} data-preview-sample={!design.announcement?.text?.trim()||undefined}>{announcementText}</p>:null,
    categories:<main key="categories">{menuSection("Browse the menu")}</main>,
    quickOrder:layoutShowsHomeQuickOrder(design.template,design.sections)?<main key="quickOrder">{menuSection(layout.id==="modern"?"Popular now":"Quick Order")}</main>:null,
    intro:<header key="intro" className="minimal-preview-intro"><p>{design.displayName}</p><h1>{design.tagline}</h1><button disabled type="button">Browse menu</button></header>,
    featured:<main key="featured">{menuSection(layout.id==="cozy"?"Featured favourites":"Today’s menu")}</main>,
  })[section]||null;
  const missing=previewMissingChecks(readiness?.checks||{},isProspect);
  return <section className={`full-design-preview template-${design.template} full-layout-${layout.id} typography-${design.typography} buttons-${design.buttonStyle}`} data-layout={layout.id} style={{"--preview-primary":design.colors.primary,"--preview-accent":design.colors.accent,"--preview-bg":design.colors.background,"--preview-surface":design.colors.surface,"--preview-text":design.colors.text}}>
    <aside className="preview-safety-banner"><strong>{setupMode?"Here’s what your customers will see":"Your app preview"}</strong><span>Preview only — customers can’t order here.</span><Link to={setupMode?"/setup/brand":"/admin/design"}>Back to editor</Link></aside>
    {setupMode&&(missing.length||isProspect)?<aside className="preview-readiness-guide"><strong>{isProspect?"Free demo":"Before you launch"}</strong>{missing.map((key)=>{const [label,to]=previewActions[key]||["Finish your store setup.","/setup/business"];return <Link key={key} to={to}>{label}</Link>;})}{isProspect?<Link to="/setup/launch">Checkout is off in the demo. Request activation when you’re ready.</Link>:null}</aside>:null}
    <nav className={`preview-navigation navigation-${layout.navigation}`}><HeaderBrandingIdentity config={design} layout={layout} logoUrl={logo?.url}/><span>{layout.id==="minimal"?"Menu · Contact · Account · Cart":layout.id==="modern"?"Home · Browse · Orders · Account · Bag":"Home · Menu · Rewards · Account · Bag"}</span></nav>
    {layout.homeSections.map(renderSection)}
  </section>;
}
