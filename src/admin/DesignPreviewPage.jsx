import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchDesignPreview } from "../services/designStudioApi.js";
import { useCatalogProducts } from "../stores/catalogStore.js";

export default function DesignPreviewPage() {
  const [preview,setPreview]=useState(null);const [error,setError]=useState("");
  const {categories,products,loading,error:catalogError}=useCatalogProducts();
  useEffect(()=>{fetchDesignPreview().then(setPreview).catch((reason)=>setError(reason.message));},[]);
  const assets=useMemo(()=>new Map((preview?.media||[]).map((asset)=>[asset.id,asset])),[preview]);
  if(error)return <section className="page-section"><h1>Draft preview unavailable</h1><p role="alert">{error}</p><Link to="/admin/design">Return to Design Studio</Link></section>;
  if(!preview||loading)return <section className="page-section"><h1>Preparing your draft preview…</h1><p>Loading the latest saved design and tenant catalog.</p></section>;
  const design=preview.design;const hero=assets.get(design.hero?.mediaId);const logo=assets.get(design.logoMediaId);
  return <section className={`full-design-preview template-${design.template}`} style={{"--preview-primary":design.colors.primary,"--preview-accent":design.colors.accent,"--preview-bg":design.colors.background,"--preview-surface":design.colors.surface,"--preview-text":design.colors.text}}>
    <aside className="preview-safety-banner"><strong>Private draft preview</strong><span>Checkout and payment are disabled.</span><Link to="/admin/design">Back to editor</Link></aside>
    <nav>{logo?<img src={logo.url} alt={logo.altText||`${design.displayName} logo`}/>:<strong>{design.displayName}</strong>}<span>Preview bag · disabled</span></nav>
    {design.announcement?.enabled&&design.announcement.text?<p className="preview-announcement">{design.announcement.text}</p>:null}
    <header style={hero?{backgroundImage:`linear-gradient(#0006,#0006),url(${hero.url})`}:undefined}><p>{design.tagline}</p><h1>{design.displayName}</h1><button disabled type="button">Preview only</button></header>
    <main>{catalogError?<p role="alert">Catalog preview unavailable: {catalogError.message}</p>:products.length?categories.map((category)=>{const items=products.filter((product)=>product.category===category.id&&product.published);return items.length?<section key={category.id}><h2>{category.name}</h2><div className={`preview-products presentation-${design.productCardPresentation}`}>{items.map((product)=><article key={product.backendId}><div/><strong>{product.name}</strong><p>{product.description}</p><span>${Number(product.price).toFixed(2)}</span></article>)}</div></section>:null;}):<section className="preview-empty"><h2>Your menu will appear here</h2><p>Add and publish products before launch.</p></section>}</main>
  </section>;
}
