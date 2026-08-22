import { getLayoutDefinition, layoutShowsHero, layoutShowsHomeQuickOrder, previewAnnouncementText, previewCatalog } from "./layoutDefinitions.js";
import PositionedSlotImage from "./PositionedSlotImage.jsx";
import HeaderBrandingIdentity from "./HeaderBrandingIdentity.jsx";
import { headerBrandingMode, heroContentVisibility } from "./imageSlotRendering.js";

function money(value) { return `$${Number(value).toFixed(2)}`; }

const areaLabels={businessName:"BUSINESS NAME",tagline:"TAGLINE",logo:"LOGO",hero:"HERO IMAGE",heroContent:"HERO CONTENT",announcement:"ANNOUNCEMENT",categories:"CATEGORIES",featured:"FEATURED",quickOrder:"QUICK ORDER",navigation:"NAVIGATION"};
function areaProps(area,designer,editable=false){
  const active=designer?.activeSlot===area||(area==="hero"&&designer?.activeSlot==="heroContent");
  if(!designer||(!active&&(!designer.showLayoutAreas||!editable)))return {};
  return {className:`designer-phone-area${active?" is-active":""}${editable?" is-editable":""}`,"data-designer-label":active&&area==="hero"&&designer.activeSlot==="heroContent"?areaLabels.heroContent:areaLabels[area],...(editable?{onClick:()=>designer.onSelectSlot?.(area),role:"button",tabIndex:0,onKeyDown:(event)=>{if(event.key==="Enter"||event.key===" ")designer.onSelectSlot?.(area);}}:{})};
}
function withArea(base,area,designer,editable=false){return `${base} ${areaProps(area,designer,editable).className||""}`.trim();}
function interactiveArea(area,designer,editable=false){const {className,...props}=areaProps(area,designer,editable);return props;}

export function PreviewHeader({ config, layout, logoUrl, designer }) {
  const mode=headerBrandingMode(config);const identitySlot=mode==="logo"?"logo":"tagline";
  const identityArea=<HeaderBrandingIdentity config={config} layout={layout} logoUrl={logoUrl} designer={Boolean(designer)} className={withArea("preview-business-name",identitySlot,designer,true)} {...interactiveArea(identitySlot,designer,true)}/>;
  if (layout.navigation === "editorial") return <nav className="layout-preview-header minimal-header">{identityArea}<span className="preview-header-actions">Menu <b>Bag</b></span></nav>;
  if (layout.navigation === "mobile-dock") return <nav className="layout-preview-header modern-header">{identityArea}<span className="preview-header-actions">Account <b>Bag</b></span></nav>;
  return <nav className="layout-preview-header cozy-header"><span>Welcome</span>{identityArea}<b>Bag</b></nav>;
}

export function FocusedHeaderBrandingPreview({config,layout,logoUrl,designer}){
  const mode=headerBrandingMode(config);const identitySlot=mode==="logo"?"logo":"tagline";
  return <div className={`focused-header-branding-preview focused-${layout.id}`}><HeaderBrandingIdentity config={config} layout={layout} logoUrl={logoUrl} designer={Boolean(designer)} className={withArea("preview-business-name",identitySlot,designer,true)} {...interactiveArea(identitySlot,designer,true)}/></div>;
}

function ProductShowcase({ layout, products }) {
  if (layout.productCards === "editorial-rows") return <div className="layout-product-list">{products.slice(0,3).map((product)=><article key={product.id}><span><strong>{product.name}</strong><small>Freshly prepared</small></span><b>{money(product.price)}</b><button type="button" disabled>+</button></article>)}</div>;
  return <div className={`layout-product-grid ${layout.productCards}`}>{products.slice(0,4).map((product,index)=><article key={product.id}><div className={`sample-product-image sample-image-${index+1}`}/><span><strong>{product.name}</strong><small>{money(product.price)}</small></span><button type="button" disabled>{layout.productCards==="media-cards"?"Add":"View"}</button></article>)}</div>;
}

export default function LayoutPhonePreview({ config, categories = [], products = [], logoUrl, heroUrl, designer = null }) {
  const layout=getLayoutDefinition(config.template);
  const catalog=previewCatalog(categories,products);
  const heroVisible=layoutShowsHero(config.template,config.sections,config.branding);
  const quickVisible=layoutShowsHomeQuickOrder(config.template,config.sections);
  const announcementText=previewAnnouncementText(config);
  const heroPosition=config.imagePositions?.hero||{x:50,y:50,zoom:1};
  const heroContent=heroContentVisibility(config.heroContent);
  const heroEmpty=designer&&!heroUrl;
  const heroFrame=heroVisible?<header data-hero-image-resolved={heroUrl?"true":"false"} className={withArea(`layout-hero hero-${layout.hero}${heroEmpty?" designer-hero-empty":""}${heroContent.cta&&layout.id==="modern"?" has-hero-content":""}`,"hero",designer,true)} style={{aspectRatio:layout.heroSlot.aspectRatio}} {...interactiveArea("hero",designer,true)}>{heroUrl?<PositionedSlotImage diagnostics={Boolean(designer)} className="layout-hero-image" src={heroUrl} position={heroPosition}/>:null}{heroEmpty?<div className="designer-hero-empty-message"><strong>HERO IMAGE</strong><small>{layout.id==="modern"?"A full-width image area":"A warm, framed image area"}</small></div>:null}{heroContent.cta&&layout.id==="modern"?<button type="button" disabled>Start an order</button>:null}</header>:null;
  return <div className={`phone-preview layout-phone-preview layout-${layout.id} typography-${config.typography} buttons-${config.buttonStyle}`} data-layout={layout.id} style={{"--preview-primary":config.colors.primary,"--preview-accent":config.colors.accent,"--preview-bg":config.colors.background,"--preview-surface":config.colors.surface,"--preview-text":config.colors.text}}>
    <div className="phone-speaker"/>
    <PreviewHeader config={config} layout={layout} logoUrl={logoUrl} designer={designer}/>
    {announcementText?<p className={withArea(`preview-announcement announcement-${layout.id}`,"announcement",designer,true)} {...interactiveArea("announcement",designer,true)} data-preview-sample={!config.announcement?.text?.trim()||undefined}>{announcementText}</p>:null}
    {layout.id==="minimal"?<section className="minimal-intro"><h2>Order simply.</h2><a>Browse menu →</a></section>:<>{heroFrame}{heroVisible&&heroContent.cta&&layout.id==="cozy"?<div className={withArea("cozy-hero-action","heroContent",designer)}><button type="button" disabled>Explore the menu</button></div>:null}</>}
    <main className="layout-preview-content">
      <section className="layout-category-section"><div className="preview-section-title"><strong>{layout.id==="minimal"?"Menu":"Browse categories"}</strong>{layout.id!=="minimal"?<span>See all</span>:null}</div><div className={`layout-categories categories-${layout.categories}`}>{catalog.categories.slice(0,3).map((category,index)=><span key={category.id}><i className={`sample-category-image sample-category-${index+1}`}/><b>{category.name}</b></span>)}</div></section>
      {layout.id==="cozy"?<section className="cozy-feature"><span>Featured favourite</span><strong>{catalog.products[0].name}</strong><button type="button" disabled>Order favourite</button></section>:null}
      {quickVisible?<section className={withArea("layout-quick-order","quickOrder",designer,layout.slots.quickOrder==="optional")} {...interactiveArea("quickOrder",designer,layout.slots.quickOrder==="optional")}><div className="preview-section-title"><strong>{layout.id==="modern"?"Popular now":"Quick Order"}</strong><span>Swipe →</span></div><div className="layout-quick-order-rail"><ProductShowcase layout={layout} products={catalog.products}/></div></section>:<section className="minimal-menu-preview"><ProductShowcase layout={layout} products={catalog.products}/><a>View the complete menu →</a></section>}
      {catalog.sample?<p className="sample-content-note">Sample menu for layout preview</p>:null}
    </main>
    {layout.navigation==="mobile-dock"?<nav className="modern-mobile-dock"><b>Home</b><span>Browse</span><span>Orders</span><span>Account</span><strong>Bag</strong></nav>:layout.navigation==="cafe-tabs"?<nav className="cozy-mobile-tabs"><b>Home</b><span>Menu</span><span>Rewards</span><span>Account</span></nav>:<footer className="minimal-footer"><span>{config.displayName}</span><span>Menu · Contact · Account</span></footer>}
  </div>;
}
