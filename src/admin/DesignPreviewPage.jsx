import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchDesignPreview, fetchReadiness } from "../services/designStudioApi.js";
import { useCatalogProducts } from "../stores/catalogStore.js";
import { getLayoutDefinition, layoutShowsHomeQuickOrder } from "../design/layoutDefinitions.js";

const previewActions = {
  business_profile:["Add your business details.","/setup/business"],
  verified_hostname:["Choose your ordering-app address.","/setup/business"],
  fulfillment:["Choose how customers can order.","/setup/ordering"],
  hours:["Add your business hours.","/setup/ordering"],
  catalog:["Add at least one menu item.","/setup/catalog"],
  clover:["Finish connecting payments.","/setup/payments"],
};

export default function DesignPreviewPage({ setupMode = false }) {
  const [preview,setPreview]=useState(null);const [error,setError]=useState("");
  const [readiness,setReadiness]=useState(null);
  const {categories,products,loading,error:catalogError}=useCatalogProducts();
  useEffect(()=>{Promise.all([fetchDesignPreview(),fetchReadiness()]).then(([nextPreview,nextReadiness])=>{setPreview(nextPreview);setReadiness(nextReadiness);}).catch((reason)=>setError(reason.message));},[]);
  const assets=useMemo(()=>new Map((preview?.media||[]).map((asset)=>[asset.id,asset])),[preview]);
  if(error)return <section className="page-section"><h1>App preview unavailable</h1><p role="alert">{error}</p><Link to="/admin/design">Return to Design Studio</Link></section>;
  if(!preview||loading)return <section className="page-section"><h1>Preparing your app preview…</h1><p>Loading your latest design and menu.</p></section>;
  const design=preview.design;const hero=assets.get(design.hero?.mediaId);const logo=assets.get(design.logoMediaId);const layout=getLayoutDefinition(design.template);
  const menuSection=(heading)=> <section className="preview-catalog-section"><h2>{heading}</h2>{catalogError?<p role="alert">Catalog preview unavailable: {catalogError.message}</p>:products.length?categories.map((category)=>{const items=products.filter((product)=>product.category===category.id&&product.published);return items.length?<section key={category.id}><h3>{category.name}</h3><div className={`preview-products presentation-${design.productCardPresentation}`}>{items.map((product)=><article key={product.backendId}><div/><strong>{product.name}</strong><p>{product.description}</p><span>${Number(product.price).toFixed(2)}</span></article>)}</div></section>:null;}):<div className="preview-empty"><h3>Your menu will appear here</h3><p>Add and publish products before launch.</p></div>}</section>;
  const renderSection=(section)=>({
    hero:<header key="hero" style={hero?{backgroundImage:`linear-gradient(#0006,#0006),url(${hero.url})`}:undefined}><p>{design.tagline}</p><h1>{design.displayName}</h1><button disabled type="button">Preview only</button></header>,
    announcement:design.announcement?.enabled&&design.announcement.text?<p key="announcement" className="preview-announcement">{design.announcement.text}</p>:null,
    categories:<main key="categories">{menuSection("Browse the menu")}</main>,
    quickOrder:layoutShowsHomeQuickOrder(design.template,design.sections)?<main key="quickOrder">{menuSection(layout.id==="modern"?"Popular now":"Quick Order")}</main>:null,
    intro:<header key="intro" className="minimal-preview-intro"><p>{design.displayName}</p><h1>{design.tagline}</h1><button disabled type="button">Browse menu</button></header>,
    featured:<main key="featured">{menuSection(layout.id==="cozy"?"Featured favourites":"Today’s menu")}</main>,
  })[section]||null;
  const missing=Object.entries(readiness?.checks||{}).filter(([key,ready])=>!ready&&key!=="published_design");
  return <section className={`full-design-preview template-${design.template} full-layout-${layout.id}`} data-layout={layout.id} style={{"--preview-primary":design.colors.primary,"--preview-accent":design.colors.accent,"--preview-bg":design.colors.background,"--preview-surface":design.colors.surface,"--preview-text":design.colors.text}}>
    <aside className="preview-safety-banner"><strong>{setupMode?"Here’s what your customers will see":"Your app preview"}</strong><span>Preview only — customers can’t order here.</span><Link to={setupMode?"/setup/brand":"/admin/design"}>Back to editor</Link></aside>
    {setupMode&&missing.length?<aside className="preview-readiness-guide"><strong>Before you launch</strong>{missing.map(([key])=>{const [label,to]=previewActions[key]||[key.replaceAll("_"," "),"/setup/business"];return <Link key={key} to={to}>{label}</Link>;})}</aside>:null}
    <nav className={`preview-navigation navigation-${layout.navigation}`}>{logo?<img src={logo.url} alt={logo.altText||`${design.displayName} logo`}/>:<strong>{design.displayName}</strong>}<span>{layout.id==="minimal"?"Menu · Contact · Account · Cart":layout.id==="modern"?"Home · Browse · Orders · Account · Bag":"Home · Menu · Rewards · Account · Bag"}</span></nav>
    {layout.homeSections.map(renderSection)}
  </section>;
}
