import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import LayoutPhonePreview, { FocusedHeaderBrandingPreview } from "../design/LayoutPhonePreview.jsx";
import PositionedSlotImage from "../design/PositionedSlotImage.jsx";
import AppIconComposition from "../design/AppIconComposition.jsx";
import AppIconCropEditor from "../design/AppIconCropEditor.jsx";
import { installedAppName, resetToLayoutColors, withInstalledAppDefaults } from "../design/installedAppDefaults.js";
import { imageRequirementForSlot, inspectImageFile, validateImageForSlot } from "../design/imageRequirements.js";
import VisualDesignerDiagnostics from "../design/VisualDesignerDiagnostics.jsx";
import { createMediaUrlIndex, headerBrandingMode, imagePositionContracts, resolveAssignedMediaUrl } from "../design/imageSlotRendering.js";
import { describeLayoutCapabilities, getLayoutDefinition, layoutChoices, layoutComparisonRows } from "../design/layoutDefinitions.js";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { archiveMedia, fetchDesignDraft, fetchDesignVersions, fetchMedia, fetchReadiness, publishDesign, revertDesign, saveDesignDraft, uploadMedia } from "../services/designStudioApi.js";
import { fetchDemoStatus } from "../services/demoFunnelApi.js";
import { useCatalogProducts } from "../stores/catalogStore.js";

const builderStages = [
  { label: "Choose your app layout", to: "/admin/design" }, { label: "Make it yours", to: "/admin/design#brand" },
  { label: "Business details", to: "/admin/setup#business" }, { label: "Build your menu", to: "/admin/products" },
  { label: "Set up ordering", to: "/admin/scheduling" }, { label: "Connect payments", to: "/admin/setup#payments" },
  { label: "Preview", to: "/admin/design/preview" }, { label: "Launch", to: "/admin/launch" }, { label: "Go Live", to: "/admin/go-live" },
];
function channel(value){const normalized=value/255;return normalized<=.04045?normalized/12.92:((normalized+.055)/1.055)**2.4;}
function luminance(color){return .2126*channel(parseInt(color.slice(1,3),16))+.7152*channel(parseInt(color.slice(3,5),16))+.0722*channel(parseInt(color.slice(5,7),16));}
function contrast(a,b){const values=[luminance(a),luminance(b)].sort((left,right)=>right-left);return(values[0]+.05)/(values[1]+.05);}

export default function DesignStudioPage({guided=false,onContinue,wizardStep=null}){
  const {session}=useOwnerAuth();const {categories,products}=useCatalogProducts();
  const designerRef=useRef(null);
  const saveInFlightRef=useRef(false);
  const [draft,setDraft]=useState(null);const [savedConfig,setSavedConfig]=useState(null);const [status,setStatus]=useState("loading");const [message,setMessage]=useState("");
  const [saveError,setSaveError]=useState("");
  const [versions,setVersions]=useState([]);const [media,setMedia]=useState([]);const [uploading,setUploading]=useState(false);const [readiness,setReadiness]=useState(null);const [mobileView,setMobileView]=useState("edit");const [imageFeedback,setImageFeedback]=useState({});
  const [activeSlot,setActiveSlot]=useState(null);const [showLayoutAreas,setShowLayoutAreas]=useState(false);const [demoStatus,setDemoStatus]=useState(null);
  const mediaById=useMemo(()=>createMediaUrlIndex(media),[media]);
  const refreshVersions=()=>fetchDesignVersions().then(setVersions);
  useEffect(()=>{Promise.all([fetchDesignDraft(),fetchDesignVersions(),fetchMedia(),fetchReadiness(),fetchDemoStatus().catch(()=>null)]).then(([value,history,assets,checks,demo])=>{setDraft({...value,config:withInstalledAppDefaults(value.config)});setSavedConfig(value.config);setVersions(history);setMedia(assets);setReadiness(checks);setDemoStatus(demo);setStatus("ready");}).catch((error)=>{setMessage(error.message);setStatus("error");});},[]);
  if(status==="loading")return <section className="page-section">
<h1>Design Studio</h1>
<p>Loading your design…</p>
</section>;
  if(!draft)return <section className="page-section">
<h1>Design Studio</h1>
<p className="owner-page-message error">{message}</p>
</section>;
  const config=draft.config;const dirty=JSON.stringify(config)!==JSON.stringify(savedConfig);const contrastValid=contrast(config.colors.text,config.colors.background)>=4.5&&contrast(config.colors.text,config.colors.surface)>=4.5;
  const update=(patch)=>setDraft((value)=>({...value,config:{...value.config,...patch}}));
  const updateBusinessName=(displayName)=>{const automatic=config.pwa.shortName==="Order"||config.pwa.shortName===installedAppName(config.displayName);update({displayName,pwa:{...config.pwa,...(automatic?{shortName:installedAppName(displayName)}:{})}});};
  const updateColor=(key,value)=>{const colors={...config.colors,[key]:value};const pwa={...config.pwa};if(key==="primary"&&(pwa.themeColor===config.colors.primary||pwa.themeColor==="#6f7d5f"))pwa.themeColor=value;if(key==="background"&&(pwa.backgroundColor===config.colors.background||pwa.backgroundColor==="#f7f0e6"))pwa.backgroundColor=value;update({colors,pwa});};
  const toggleSection=(section,enabled)=>update({sections:enabled?[...config.sections,section]:config.sections.filter((item)=>item!==section)});
  const mediaUrl=(id)=>resolveAssignedMediaUrl(mediaById,id);
  async function selectLayout(template){if(template===config.template||status!=="ready")return;const nextConfig={...config,template};setDraft((value)=>({...value,config:nextConfig}));if(wizardStep!=="look")return;try{setStatus("saving");setMessage("");const value=await saveDesignDraft({revision:draft.revision,config:nextConfig},session.csrf_token);setDraft(value);setSavedConfig(value.config);setMessage(`${layoutChoices.find((item)=>item.id===template)?.name} layout selected. You’ll add your brand next.`);setStatus("ready");}catch(error){setDraft((value)=>({...value,config:savedConfig}));setMessage(error.message);setStatus("error");}}
  async function save(){if(saveInFlightRef.current||status!=="ready"||!dirty)return;saveInFlightRef.current=true;setSaveError("");try{setStatus("saving");const value=await saveDesignDraft({revision:draft.revision,config},session.csrf_token);setDraft(value);setSavedConfig(value.config);setMessage("Design saved. Your live app is unchanged until you publish.");setStatus("ready");}catch(error){setMessage(error.message);setSaveError(error.message);setStatus("ready");}finally{saveInFlightRef.current=false;}}
  async function publish(){if(dirty){setMessage("Save your changes before publishing so the app you reviewed is the version that goes live.");return;}if(!globalThis.confirm?.("Publish this saved design to your customer app now?"))return;try{setStatus("publishing");const value=await publishDesign(session.csrf_token);await refreshVersions();setReadiness(await fetchReadiness());setMessage(`Version ${value.version} is now live. Your menu, prices, and orders were not changed.`);setStatus("ready");}catch(error){setMessage(error.message);setStatus("error");}}
  async function revert(item){if(!globalThis.confirm?.(`Restore version ${item.version}? Your menu and orders will not change.`))return;try{setStatus("publishing");const value=await revertDesign(item.id,session.csrf_token);const[nextDraft]=await Promise.all([fetchDesignDraft(),refreshVersions()]);setDraft(nextDraft);setSavedConfig(nextDraft.config);setMessage(`Version ${value.version} is live, restored from version ${item.version}.`);setStatus("ready");}catch(error){setMessage(error.message);setStatus("error");}}
  const slotRequirement=(slot)=>imageRequirementForSlot(selectedLayout.id,slot);
  const assignSlot=(slot,id)=>update(slot==="logo"?{logoMediaId:id}:slot==="hero"?{hero:{mode:id?"image":"color",mediaId:id}}:{appIconMediaId:id});
  const checkAsset=(slot,asset)=>{const requirement=slotRequirement(slot);const result=asset?.width&&asset?.height?validateImageForSlot({type:asset.mediaType,size:asset.byteSize,width:asset.width,height:asset.height},requirement):{errors:[],warnings:[]};setImageFeedback((value)=>({...value,[slot]:result}));return result;};
  const chooseSlot=(slot,id)=>{const asset=media.find((item)=>item.id===id);if(asset)checkAsset(slot,asset);else setImageFeedback((value)=>({...value,[slot]:{errors:[],warnings:[]}}));assignSlot(slot,id||null);};
  async function uploadForSlot(event,slot){const file=event.target.files?.[0];if(!file)return;try{setUploading(true);const details=await inspectImageFile(file);const result=validateImageForSlot(details,slotRequirement(slot));setImageFeedback((value)=>({...value,[slot]:result}));if(result.errors.length)return;const asset=await uploadMedia(file,`${config.displayName} ${slot}`,session.csrf_token);setMedia((items)=>[asset,...items]);assignSlot(slot,asset.id);setMessage(`${slotRequirement(slot).label} uploaded and assigned.`);}catch(error){setImageFeedback((value)=>({...value,[slot]:{errors:[error.message||"This image could not be read."],warnings:[]}}));}finally{setUploading(false);event.target.value="";}}
  const updatePosition=(slot,patch)=>update({imagePositions:{...config.imagePositions,[slot]:{...config.imagePositions[slot],...patch}}});
  const resetPosition=(slot)=>updatePosition(slot,{x:50,y:50,zoom:1});
  const setBrandingVisibility=(key,visible)=>update({branding:{...config.branding,[key]:visible}});
  const setHeaderMode=(headerMode)=>update({branding:{...config.branding,headerMode,showLogo:headerMode==="logo"}});
  const selectPhoneArea=(slot)=>{setActiveSlot(slot);const selectors={logo:"#designer-slot-logo",hero:"#designer-slot-hero",announcement:"#designer-slot-announcement",quickOrder:"#designer-slot-quick-order"};designerRef.current?.querySelector(selectors[slot])?.scrollIntoView?.({behavior:"smooth",block:"center"});};
  async function removeMedia(asset){if(!globalThis.confirm?.(`Remove ${asset.altText||"this image"} from your library?`))return;try{await archiveMedia(asset.id,session.csrf_token);setMedia((items)=>items.filter((item)=>item.id!==asset.id));setMessage("Image removed from your library.");}catch(error){setMessage(error.message);}}
  const selectedLayout=getLayoutDefinition(config.template);const showLayoutControls=wizardStep!=="brand";const showCustomization=wizardStep!=="look";
  const positionControls=(slot)=>
<div className={`image-position-controls position-${slot}`}><strong>Position your {slot==="appIcon"?"app icon":slot==="logo"?"header logo":slot}</strong>
<label>Left / right<input type="range" min={imagePositionContracts[slot].minX} max={imagePositionContracts[slot].maxX} value={config.imagePositions[slot].x} onChange={(event)=>updatePosition(slot,{x:Number(event.target.value)})}/>
</label>
<label>Up / down<input type="range" min={imagePositionContracts[slot].minY} max={imagePositionContracts[slot].maxY} value={config.imagePositions[slot].y} onChange={(event)=>updatePosition(slot,{y:Number(event.target.value)})}/>
</label>
<label>Zoom<input type="range" min={imagePositionContracts[slot].minZoom} max={imagePositionContracts[slot].maxZoom} step=".05" value={config.imagePositions[slot].zoom} onChange={(event)=>updatePosition(slot,{zoom:Number(event.target.value)})}/>
</label>
<button className="text-button" type="button" onClick={()=>resetPosition(slot)}>Reset position</button>
<small>Position is saved with your design; the original image is never changed.</small>
</div>;
  const feedback=(slot)=>imageFeedback[slot]?.errors?.length||imageFeedback[slot]?.warnings?.length?<div className="image-feedback" role="status">{imageFeedback[slot].errors?.map((item)=>
<p className="error" key={item}>{item}</p>)}{imageFeedback[slot].warnings?.map((item)=>
<p className="warning" key={item}>{item}</p>)}</div>:null;
  const reviewHostname=["localhost","127.0.0.1"].includes(globalThis.location?.hostname)||globalThis.location?.hostname?.endsWith(".github.dev");
  const showLocalDiagnostics=import.meta.env.DEV&&reviewHostname;
  return <section ref={designerRef} className={`design-studio visual-designer-shell ${wizardStep?`embedded-wizard-design wizard-design-${wizardStep}`:""}`}>
    {guided&&!wizardStep?<nav className="builder-progress" aria-label="Build your app progress">{builderStages.map((stage,index)=>
<Link className={index<2?"active":""} key={stage.label} to={stage.to}>
<span>{index+1}</span>{stage.label}</Link>)}</nav>:null}
    {demoStatus?.isProspect?<aside className="demo-prospect-banner" role="status"><strong>Free demo mode</strong><span>Real orders and payments are locked. Preview anytime, then <Link to="/setup/launch">request activation</Link> (~{demoStatus.pricing?.amountDisplay || "CAD $150/month"}, JDS takes 0% of sales).</span></aside>:null}
    <header className="design-studio-header">
<div>
<p className="eyebrow">{wizardStep==="look"?"Step 1":wizardStep==="brand"?"Step 2":guided?"Welcome to JDS":"Your storefront"}</p>
<h1>{wizardStep==="look"?"Choose your app layout.":wizardStep==="brand"?"Now make it yours.":guided?"Let’s build your ordering app.":"Design Studio"}</h1>
<p>{wizardStep==="look"?"Choose how your ordering app is organized. You’ll add your logo, colours and photos next.":wizardStep==="brand"?"Add your name, colours, images, and personality while your app updates beside you.":guided?"Start with a layout you love, then make every detail feel like your business.":"Change your app layout or branding anytime. Your menu, prices, and availability stay intact."}</p>
<p className={`draft-state ${dirty?"unsaved":"saved"}`}>{dirty?"Changes not saved yet · your live app is unchanged":"Your design is saved"}</p>
</div>
<div className="design-actions">{!wizardStep?<Link className="secondary-button" to="/admin/design/preview">Full preview</Link>:null}{wizardStep!=="look"?<button aria-busy={status==="saving"} className="primary-button" disabled={status!=="ready"||!dirty} onClick={save}>{status==="saving"?"Saving…":"Save my design"}</button>:null}{!guided?<button className="primary-button" disabled={status!=="ready"||dirty||!readiness?.checks} onClick={publish}>{status==="publishing"?"Publishing…":"Publish saved design"}</button>:null}</div>
</header>
    {message?<p className="owner-page-message" aria-live="polite">{message}</p>:null}<div className="mobile-studio-toggle" role="group" aria-label="Design workspace view">
<button className={mobileView==="edit"?"active":""} onClick={()=>setMobileView("edit")} type="button">Edit</button>
<button className={mobileView==="preview"?"active":""} onClick={()=>setMobileView("preview")} type="button">Preview</button>
</div>
    <label className="show-layout-areas"><input type="checkbox" checked={showLayoutAreas} onChange={(event)=>setShowLayoutAreas(event.target.checked)}/>Show layout areas <small>Editor guidance only</small></label>
    <div className={`studio-workspace visual-designer-workspace mobile-${mobileView}`}>
<aside className="studio-controls visual-designer-editor" aria-label="Design controls">
      {showLayoutControls?<>
<fieldset className="look-chooser layout-choice-grid">
<legend>{guided?"Choose your app layout":"Choose an app layout"}</legend>
<p className="field-help">Choose the structure that best fits how customers browse and order. Your menu, prices, and availability stay the same.</p>{layoutChoices.map((item)=>{const capabilities=describeLayoutCapabilities(item);return <label className={`layout-choice-card layout-choice-${item.id}`} key={item.id}>
<input disabled={status!=="ready"} type="radio" name="template" checked={config.template===item.id} onChange={()=>selectLayout(item.id)}/>
<span className="layout-card-miniature" aria-hidden="true">
<i className="mini-header"/>
<i className="mini-hero"/>
<i className="mini-categories"/>
<i className="mini-products"/>
<i className="mini-nav"/>
</span>
<span className="layout-card-copy">
<strong>{item.name}</strong>
<b>{item.personality}</b>
<small>{item.summary}</small>
<ul>{[capabilities.hero,capabilities.quickOrder,capabilities.products,capabilities.orderingAction,capabilities.mobileNavigation].map((text)=>
<li key={text}>{text}</li>)}</ul>
</span>
<span className="layout-selected-mark">{config.template===item.id?"Selected":"Choose"}</span>
</label>})}</fieldset>
<details className="layout-comparison">
<summary>Compare layouts</summary>
<div className="layout-comparison-scroll">
<table>
<thead>
<tr>
<th scope="col">Feature</th>{layoutChoices.map((layout)=>
<th scope="col" key={layout.id}>{layout.name}</th>)}</tr>
</thead>
<tbody>{layoutComparisonRows.map((row)=>
<tr key={row.key}>
<th scope="row">{row.label}</th>{layoutChoices.map((layout)=>
<td key={layout.id}>{row.values[layout.id]}</td>)}</tr>)}</tbody>
</table>
</div>
</details>
</>:null}
      {showCustomization?<>
        {guided?<div className="builder-section-heading" id="brand">
<span>2</span>
<div>
<h2>Make it yours</h2>
<p>Bring in your name, colours, images, and personality.</p>
</div>
</div>:null}
        <fieldset className="designer-control-group">
<legend>Your brand</legend>
<p className="field-help">The name, message, and logo customers recognize.</p>
<label>Business or app name<input value={config.displayName} maxLength="80" onFocus={()=>setActiveSlot("businessName")} onChange={(event)=>updateBusinessName(event.target.value)}/>
</label>
<label>Tagline<input value={config.tagline} maxLength="140" onFocus={()=>setActiveSlot("tagline")} onChange={(event)=>update({tagline:event.target.value})}/>
<small className="field-help">This can be your primary header branding. It is not placed over your Hero artwork.</small>
</label>
<section id="designer-slot-logo" className="purpose-image-control" onFocusCapture={()=>setActiveSlot(headerBrandingMode(config)==="logo"?"logo":"tagline")}>
<h3>Header branding</h3><p>Choose what appears at the top of your app.</p>
<div className="header-branding-choice" role="radiogroup" aria-label="Header branding"><label><input type="radio" name="headerBranding" checked={headerBrandingMode(config)==="logo"} onChange={()=>setHeaderMode("logo")}/>Logo</label><label><input type="radio" name="headerBranding" checked={headerBrandingMode(config)==="tagline"} onChange={()=>setHeaderMode("tagline")}/>Tagline</label></div>
{headerBrandingMode(config)==="logo"?<>
<h3>Header logo</h3>
<p>This logo appears inside the header of your ordering app.</p>
<ul className="image-guidance">
<li>Transparent PNG or WebP recommended</li>
<li>Horizontal shape, about 3:1</li>
<li>At least 600 × 200 pixels</li>
<li>Up to 10 MB</li>
</ul>
<label className="secondary-button upload-button">Upload header logo<input type="file" accept="image/png,image/jpeg,image/webp" disabled={uploading} onChange={(event)=>uploadForSlot(event,"logo")}/>
</label>
<label>Choose existing image<select value={config.logoMediaId||""} onChange={(event)=>chooseSlot("logo",event.target.value)}>
<option value="">No logo selected</option>{media.map((asset)=>
<option key={asset.id} value={asset.id}>{asset.altText||asset.storageKey||"Uploaded image"}</option>)}</select>
</label>{feedback("logo")}{config.logoMediaId?<>
<strong>Position your header logo</strong><p className="field-help">This enlarged frame matches the logo area in your selected layout.</p><div className={`slot-image-preview logo-slot-preview logo-slot-${selectedLayout.id}`} aria-label="Header Logo final crop preview" style={{aspectRatio:selectedLayout.logoSlot.aspectRatio}}>
<PositionedSlotImage src={mediaUrl(config.logoMediaId)} alt="Current logo" position={config.imagePositions.logo} fit="contain"/>
</div>{positionControls("logo")}<button className="text-button" type="button" onClick={()=>chooseSlot("logo",null)}>Remove logo</button>
</>:null}</>:<p className="field-help layout-rule-note">Your saved Header Logo and its position are preserved while your Tagline appears in the header.</p>}<div className="header-context-preview" aria-label="Header Preview"><strong>Header Preview</strong><p className="field-help">A focused view of the branding slot. The phone shows the complete header.</p><FocusedHeaderBrandingPreview config={config} layout={selectedLayout} logoUrl={mediaUrl(config.logoMediaId)} designer={{activeSlot:headerBrandingMode(config)==="logo"?"logo":"tagline"}}/></div></section>
</fieldset>
        <fieldset className="designer-control-group">
<legend>Colours &amp; style</legend>
<p className="field-help">These choices update your app preview immediately.</p><button className="text-button" type="button" onClick={()=>setDraft((value)=>({...value,config:resetToLayoutColors(value.config,selectedLayout)}))}>Reset to layout colours</button>
<div className="color-controls">{Object.entries(config.colors).map(([key,value])=>
<label key={key}>{key}<input type="color" value={value} onChange={(event)=>updateColor(key,event.target.value)}/>
</label>)}</div>{!contrastValid?<p className="owner-page-message error" role="alert">This text colour may be difficult for customers to read. Choose a darker colour or Reset to layout colours before saving.</p>:null}<label>Typography<select value={config.typography} onChange={(event)=>update({typography:event.target.value})}>
<option value="modern">Modern</option>
<option value="classic">Classic</option>
<option value="friendly">Friendly</option>
</select>
</label>
<label>Button style<select value={config.buttonStyle} onChange={(event)=>update({buttonStyle:event.target.value})}>
<option value="rounded">Rounded</option>
<option value="square">Square</option>
<option value="pill">Pill</option>
</select>
</label>
</fieldset>
        <fieldset className="designer-control-group">
<legend>Images</legend>{selectedLayout.slots.hero!=="unsupported"?<section id="designer-slot-hero" className="purpose-image-control" onFocusCapture={()=>setActiveSlot("hero")} onMouseDown={()=>setActiveSlot("hero")}>
<h3>Hero image</h3>
<p>The large image customers see near the top of your Home screen.</p>
<label className="checkbox-label slot-visibility-toggle"><input type="checkbox" checked={config.branding.showHero} onChange={(event)=>setBrandingVisibility("showHero",event.target.checked)}/>Show hero image</label>
{config.branding.showHero?<>
<label onFocus={()=>setActiveSlot("heroContent")}>Hero content<select value={config.heroContent} onChange={(event)=>update({heroContent:event.target.value})}>
<option value="image">Image only</option>
<option value="cta">Image + ordering button</option>
</select><small className="field-help">Choose whether the layout adds its ordering action to your artwork. Your Tagline stays in the header.</small></label>
<p>{slotRequirement("hero").guidance} {slotRequirement("hero").fit}</p>
<ul className="image-guidance">
<li>PNG, JPEG, or WebP</li>
<li>{selectedLayout.id==="modern"?"Wide 16:9 shape":"Wide 2:1 shape"}</li>
<li>At least {slotRequirement("hero").minWidth} × {slotRequirement("hero").minHeight} pixels</li>
<li>Up to 10 MB</li>
</ul>
<label className="secondary-button upload-button">Upload hero image<input type="file" accept="image/png,image/jpeg,image/webp" disabled={uploading} onChange={(event)=>uploadForSlot(event,"hero")}/>
</label>
<label>Choose from library<select value={config.hero?.mediaId||""} onChange={(event)=>chooseSlot("hero",event.target.value)}>
<option value="">Use brand colour</option>{media.map((asset)=>
<option key={asset.id} value={asset.id}>{asset.altText||asset.storageKey||"Uploaded image"}</option>)}</select>
</label>{feedback("hero")}{config.hero?.mediaId?<>
<strong>Position your hero</strong><p className="field-help">What you see inside this frame is the crop customers will see.</p><div className={`slot-image-preview hero-slot-preview hero-slot-${selectedLayout.id}`} aria-label="Hero final crop preview" style={{aspectRatio:selectedLayout.heroSlot.aspectRatio}}>
<PositionedSlotImage src={mediaUrl(config.hero.mediaId)} alt="Current hero" position={config.imagePositions.hero}/>
</div>{positionControls("hero")}<button className="text-button" type="button" onClick={()=>chooseSlot("hero",null)}>Remove hero image</button>
</>:null}</>:<p className="field-help layout-rule-note">Your homepage content moves up automatically while the hero is hidden.</p>}</section>:<p className="field-help">Minimal uses a text-first introduction and does not have a large hero image.</p>}<details className="media-library-details">
<summary>Browse full image library</summary>{media.length?<div className="media-library-grid">{media.map((asset)=>{const assigned=[config.logoMediaId,config.hero?.mediaId,config.appIconMediaId].includes(asset.id);return <article className={assigned?"is-assigned":""} key={asset.id}>
<img src={asset.ownerUrl} alt={asset.altText||"Uploaded brand image"}/>
<span>{asset.altText||"Brand image"}{assigned?" · In use":""}</span>
<button type="button" className="text-button" disabled={assigned} onClick={()=>removeMedia(asset)}>Remove</button>
</article>;})}</div>:<p className="preview-empty">No images uploaded yet.</p>}</details>
</fieldset>
        <fieldset className="designer-control-group">
<legend>Homepage</legend>
<p className="field-help">Choose the supported content customers see when they open your app.</p>
<section id="designer-slot-quick-order" className="designer-control-subgroup" onFocusCapture={()=>setActiveSlot("quickOrder")} onMouseDown={()=>setActiveSlot("quickOrder")}>
<h3>Quick Order</h3>
<p className="field-help">Makes it easy for returning customers to reorder items they buy regularly. JDS builds it from each customer’s purchase history.</p>{selectedLayout.quickOrder==="home-cards"?<label className="checkbox-label">
<input type="checkbox" checked={config.sections.includes("quickOrder")} onChange={(event)=>toggleSection("quickOrder",event.target.checked)}/>Show Quick Order on Home</label>:<p className="field-help layout-rule-note">{describeLayoutCapabilities(selectedLayout).quickOrder}</p>}</section>
<section id="designer-slot-announcement" className="designer-control-subgroup" onFocusCapture={()=>setActiveSlot("announcement")} onMouseDown={()=>setActiveSlot("announcement")}>
<h3>Announcements</h3>
<label className="checkbox-label">
<input type="checkbox" checked={config.announcement?.enabled||false} onChange={(event)=>update({announcement:{...(config.announcement||{text:""}),enabled:event.target.checked}})}/>Show announcements on my app</label>{config.announcement?.enabled?<label>Announcement text<input placeholder="Weekend special available now" value={config.announcement?.text||""} maxLength="180" onChange={(event)=>update({announcement:{...(config.announcement||{enabled:true}),text:event.target.value}})}/>
<small className="field-help">If left blank, sample text appears only in previews.</small>
</label>:null}</section>
</fieldset>
        <fieldset className="designer-control-group installed-app-group">
<legend>When customers install your app</legend>
<p className="field-help">Customize how your ordering app appears on your customers’ phones.</p>
<section className="purpose-image-control">
<h3>App icon</h3>
<p>This is the icon customers see when they add your ordering app to their phone.</p>
<h4 className="app-icon-source-heading">Source</h4>
<ul className="image-guidance">
<li>Square 1:1 PNG or WebP recommended</li>
<li>At least 512 × 512 pixels</li>
<li>Use the crop editor to choose exactly what appears</li>
<li>Up to 10 MB</li>
</ul>
<label className="secondary-button upload-button">Upload app icon<input type="file" accept="image/png,image/jpeg,image/webp" disabled={uploading} onChange={(event)=>uploadForSlot(event,"appIcon")}/>
</label>
<button className="secondary-button" type="button" disabled={!config.logoMediaId} onClick={()=>chooseSlot("appIcon",config.logoMediaId)}>Use my logo</button>
<small className="field-help">Uses the assigned Header Logo image as a source, then gives it an independent square App Icon crop. Your Header Logo is not changed.</small>
<label>Choose from my images<select value={config.appIconMediaId||""} onChange={(event)=>chooseSlot("appIcon",event.target.value)}>
<option value="">Use generated brand icon</option>{media.map((asset)=>
<option key={asset.id} value={asset.id}>{asset.altText||asset.storageKey||"Uploaded image"}</option>)}</select>
</label>{feedback("appIcon")}{config.appIconMediaId?null:<p className="field-help fallback-status">Generated brand-colour fallback currently in use. Choose an image whenever you’re ready.</p>}
<label>Name under the icon<input value={config.pwa.shortName} maxLength="30" onChange={(event)=>update({pwa:{...config.pwa,shortName:event.target.value}})}/>
<small className="field-help">This is the name customers see under your app icon. We use your business name automatically; shorten it only if useful.</small>
</label>
<div className="app-icon-workspace">
<section className="app-icon-editor-pane"><h4>Position your app icon</h4><p>Everything inside the dotted Icon Crop box will appear in your app icon. Anything outside will be cropped out.</p>{config.appIconMediaId?<><AppIconCropEditor config={config} src={mediaUrl(config.appIconMediaId)}/>{positionControls("appIcon")}<button className="text-button" type="button" onClick={()=>chooseSlot("appIcon",null)}>Use generated fallback</button></>:<div className="app-icon-empty-editor"><AppIconComposition config={config} src={null}/><span>Generated fallback — choose an image to position it here.</span></div>}</section>
<aside className="app-icon-results"><section className="final-app-icon-preview"><h4>Your app icon</h4><AppIconComposition config={config} src={mediaUrl(config.appIconMediaId)} className="final-icon-artwork"/><small>{config.appIconMediaId?"Your selected image with its App Icon position.":"Generated from your brand colours."}</small></section><section className="installed-app-customer-preview"><h4>What customers see</h4><p>Your app icon with the name shown on their phone.</p><div className="installed-app-preview" aria-label="Installed app customer preview"><AppIconComposition config={config} src={mediaUrl(config.appIconMediaId)}/><strong>{config.pwa.shortName}</strong></div></section></aside>
</div></section>
<div className="installed-app-colour-summary">
<span>
<i style={{background:config.pwa.themeColor}}/>Phone accent colour<small>Uses your primary brand colour</small>
</span>
<span>
<i style={{background:config.pwa.backgroundColor}}/>Opening screen colour<small>Uses your app background colour</small>
</span>
</div>
</fieldset>
      </>:null}
      {guided?<aside className="builder-next" id={wizardStep==="brand"?"step2-next":undefined}>
<span>Next</span>
<strong>{wizardStep==="look"?"Make this layout yours":"Tell us about your business"}</strong>
<p>{wizardStep==="look"?"Your layout choice saves automatically. Next, add your logo, colours and photos.":"Save your design, then add the details customers need to order with confidence."}</p>
{wizardStep==="brand"?<div className="builder-next-save"><p className={`draft-state ${dirty?"unsaved":"saved"}`} aria-live="polite">{status==="saving"?"Saving your design…":dirty?"Unsaved changes":"Your design is saved ✓"}</p>{saveError?<p className="owner-page-message error" role="alert">Your design was not saved. {saveError}</p>:null}<button aria-busy={status==="saving"} className="primary-button" disabled={status!=="ready"||!dirty} type="button" onClick={save}>{status==="saving"?"Saving…":"Save my design"}</button></div>:null}
{wizardStep?<button className={wizardStep==="brand"&&!dirty?"primary-button":"secondary-button"} disabled={dirty||status!=="ready"} type="button" onClick={onContinue}>{wizardStep==="look"?"Continue to branding":"Continue to business details"}</button>:<Link className={`primary-button ${dirty?"disabled-link":""}`} aria-disabled={dirty} to={dirty?"#brand":"/admin/setup#business"}>Continue to business details</Link>}</aside>:<section className="design-history">
<h2>Published versions</h2>{versions.length?<ul>{versions.map((item)=>
<li key={item.id}>
<span>Version {item.version}{item.isCurrent?" · Live":""}<small>{new Date(item.publishedAt).toLocaleString()}</small>
</span>{!item.isCurrent?<button className="secondary-button" type="button" disabled={status!=="ready"} onClick={()=>revert(item)}>Restore</button>:null}</li>)}</ul>:<p>Nothing has been published yet.</p>}</section>}
    </aside>
<div className="phone-preview-column visual-designer-preview-column">
<div className="phone-preview-wrap phone-preview-sticky visual-designer-preview-sticky">
<p className="preview-badge">Your app preview</p>
<LayoutPhonePreview config={config} categories={categories} products={products} logoUrl={mediaUrl(config.logoMediaId)} heroUrl={mediaUrl(config.hero?.mediaId)} designer={{activeSlot,showLayoutAreas,onSelectSlot:selectPhoneArea}}/>
<p className="preview-only-note">Preview only — customers can’t order yet.</p>{showLocalDiagnostics?<VisualDesignerDiagnostics rootRef={designerRef}/>:null}</div>
</div>
</div>
  </section>;
}
