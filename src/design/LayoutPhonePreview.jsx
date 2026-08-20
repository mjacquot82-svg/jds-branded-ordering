import { getLayoutDefinition, layoutShowsHero, layoutShowsHomeQuickOrder, previewCatalog } from "./layoutDefinitions.js";

function money(value) { return `$${Number(value).toFixed(2)}`; }

function PreviewHeader({ config, layout, logoUrl }) {
  if (layout.navigation === "editorial") return <nav className="layout-preview-header minimal-header"><span>{logoUrl?<img src={logoUrl} alt=""/>:<strong>{config.displayName}</strong>}</span><span>Menu&nbsp;&nbsp; Bag</span></nav>;
  if (layout.navigation === "mobile-dock") return <nav className="layout-preview-header modern-header"><span>{logoUrl?<img src={logoUrl} alt=""/>:<strong>{config.displayName}</strong>}</span><span className="preview-header-actions">Account <b>Bag</b></span></nav>;
  return <nav className="layout-preview-header cozy-header"><span>Welcome</span>{logoUrl?<img src={logoUrl} alt=""/>:<strong>{config.displayName}</strong>}<b>Bag</b></nav>;
}

function ProductShowcase({ layout, products }) {
  if (layout.productCards === "editorial-rows") return <div className="layout-product-list">{products.slice(0,3).map((product)=><article key={product.id}><span><strong>{product.name}</strong><small>Freshly prepared</small></span><b>{money(product.price)}</b><button type="button" disabled>+</button></article>)}</div>;
  return <div className={`layout-product-grid ${layout.productCards}`}>{products.slice(0,4).map((product,index)=><article key={product.id}><div className={`sample-product-image sample-image-${index+1}`}/><span><strong>{product.name}</strong><small>{money(product.price)}</small></span><button type="button" disabled>{layout.productCards==="media-cards"?"Add":"View"}</button></article>)}</div>;
}

export default function LayoutPhonePreview({ config, categories = [], products = [], logoUrl, heroUrl }) {
  const layout=getLayoutDefinition(config.template);
  const catalog=previewCatalog(categories,products);
  const heroVisible=layoutShowsHero(config.template,config.sections);
  const quickVisible=layoutShowsHomeQuickOrder(config.template,config.sections);
  return <div className={`phone-preview layout-phone-preview layout-${layout.id}`} data-layout={layout.id} style={{"--preview-primary":config.colors.primary,"--preview-accent":config.colors.accent,"--preview-bg":config.colors.background,"--preview-surface":config.colors.surface,"--preview-text":config.colors.text}}>
    <div className="phone-speaker"/>
    <PreviewHeader config={config} layout={layout} logoUrl={logoUrl}/>
    {config.announcement?.enabled&&config.announcement.text?<p className="preview-announcement">{config.announcement.text}</p>:null}
    {layout.id==="minimal"?<section className="minimal-intro"><p>{config.tagline}</p><h2>Order simply.</h2><a>Browse menu →</a></section>:heroVisible?<header className={`layout-hero hero-${layout.hero}`} style={heroUrl?{backgroundImage:`linear-gradient(#0006,#0006),url(${heroUrl})`}:undefined}><p>{layout.id==="modern"?"Order ahead from":config.tagline}</p><h2>{config.displayName}</h2><button type="button" disabled>{layout.id==="modern"?"Start an order":"Explore the menu"}</button></header>:null}
    <main className="layout-preview-content">
      <section className="layout-category-section"><div className="preview-section-title"><strong>{layout.id==="minimal"?"Menu":"Browse categories"}</strong>{layout.id!=="minimal"?<span>See all</span>:null}</div><div className={`layout-categories categories-${layout.categories}`}>{catalog.categories.slice(0,3).map((category,index)=><span key={category.id}><i className={`sample-category-image sample-category-${index+1}`}/><b>{category.name}</b></span>)}</div></section>
      {layout.id==="cozy"?<section className="cozy-feature"><span>Featured favourite</span><strong>{catalog.products[0].name}</strong><button type="button" disabled>Order favourite</button></section>:null}
      {quickVisible?<section className="layout-quick-order"><div className="preview-section-title"><strong>{layout.id==="modern"?"Popular now":"Quick Order"}</strong><span>Swipe →</span></div><ProductShowcase layout={layout} products={catalog.products}/></section>:<section className="minimal-menu-preview"><ProductShowcase layout={layout} products={catalog.products}/><a>View the complete menu →</a></section>}
      {catalog.sample?<p className="sample-content-note">Sample menu for layout preview</p>:null}
    </main>
    {layout.navigation==="mobile-dock"?<nav className="modern-mobile-dock"><b>Home</b><span>Browse</span><span>Orders</span><span>Account</span><strong>Bag</strong></nav>:layout.navigation==="cafe-tabs"?<nav className="cozy-mobile-tabs"><b>Home</b><span>Menu</span><span>Rewards</span><span>Account</span></nav>:<footer className="minimal-footer"><span>{config.displayName}</span><span>Menu · Contact · Account</span></footer>}
  </div>;
}
