import { useEffect, useMemo, useState } from "react";
import { fetchDesignDraft, fetchDesignVersions, publishDesign, revertDesign, saveDesignDraft } from "../services/designStudioApi.js";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { useCatalogProducts } from "../stores/catalogStore.js";

const templates = [
  { id: "modern", name: "Modern", note: "Bold hero, horizontal categories, crisp product grid" },
  { id: "minimal", name: "Minimal", note: "Compact navigation, editorial spacing, quiet cards" },
  { id: "cozy", name: "Cozy", note: "Warm hero, welcoming sections, comfortable cards" },
];
export default function DesignStudioPage() {
  const { session } = useOwnerAuth(); const { products } = useCatalogProducts();
  const [draft, setDraft] = useState(null); const [status, setStatus] = useState("loading"); const [message, setMessage] = useState("");
  const [versions, setVersions] = useState([]);
  const refreshVersions = () => fetchDesignVersions().then(setVersions);
  useEffect(() => { Promise.all([fetchDesignDraft(), fetchDesignVersions()]).then(([value, history]) => { setDraft(value); setVersions(history); setStatus("ready"); }).catch((error) => { setMessage(error.message); setStatus("error"); }); }, []);
  const sample = useMemo(() => products.filter((p) => p.published).slice(0, 4), [products]);
  if (status === "loading") return <section className="page-section"><h1>Design Studio</h1><p>Loading your draft…</p></section>;
  if (!draft) return <section className="page-section"><h1>Design Studio</h1><p className="owner-page-message error">{message}</p></section>;
  const config = draft.config;
  const update = (patch) => setDraft((value) => ({ ...value, config: { ...value.config, ...patch } }));
  async function save() { try { setStatus("saving"); const value=await saveDesignDraft({ revision:draft.revision, config },session.csrf_token); setDraft(value); setMessage("Draft saved. Your public storefront is unchanged."); setStatus("ready"); } catch(error){setMessage(error.message);setStatus("error");} }
  async function publish(){ try{setStatus("publishing");const value=await publishDesign(session.csrf_token);await refreshVersions();setMessage(`Version ${value.version} is now live.`);setStatus("ready");}catch(error){setMessage(error.message);setStatus("error");} }
  async function revert(item){ if (!globalThis.confirm?.(`Restore version ${item.version}? Your menu and orders will not change.`)) return; try{setStatus("publishing");const value=await revertDesign(item.id,session.csrf_token);const [nextDraft]=await Promise.all([fetchDesignDraft(),refreshVersions()]);setDraft(nextDraft);setMessage(`Version ${value.version} is live, restored from version ${item.version}.`);setStatus("ready");}catch(error){setMessage(error.message);setStatus("error");} }
  return <section className="design-studio">
    <header className="design-studio-header"><div><p className="eyebrow">Your storefront</p><h1>Design Studio</h1><p>Customize a guided template. Menu, prices, and availability always stay live.</p></div><div className="design-actions"><button className="secondary-button" disabled={status!=="ready"} onClick={save}>Save draft</button><button className="primary-button" disabled={status!=="ready"} onClick={publish}>Publish</button></div></header>
    {message ? <p className="owner-page-message" aria-live="polite">{message}</p> : null}
    <div className="studio-workspace"><aside className="studio-controls" aria-label="Design controls">
      <fieldset><legend>Template</legend>{templates.map((item)=><label className="template-choice" key={item.id}><input type="radio" name="template" checked={config.template===item.id} onChange={()=>update({template:item.id})}/><span><strong>{item.name}</strong><small>{item.note}</small></span></label>)}</fieldset>
      <label>Business name<input value={config.displayName} maxLength="80" onChange={(e)=>update({displayName:e.target.value})}/></label>
      <label>Tagline<input value={config.tagline} maxLength="140" onChange={(e)=>update({tagline:e.target.value})}/></label>
      <div className="color-controls">{Object.entries(config.colors).map(([key,value])=><label key={key}>{key}<input type="color" value={value} onChange={(e)=>update({colors:{...config.colors,[key]:e.target.value}})}/></label>)}</div>
      <label>Typography<select value={config.typography} onChange={(e)=>update({typography:e.target.value})}><option value="modern">Modern</option><option value="classic">Classic</option><option value="friendly">Friendly</option></select></label>
      <label>Button style<select value={config.buttonStyle} onChange={(e)=>update({buttonStyle:e.target.value})}><option value="rounded">Rounded</option><option value="square">Square</option><option value="pill">Pill</option></select></label>
      <section className="design-history"><h2>Published versions</h2>{versions.length ? <ul>{versions.map((item)=><li key={item.id}><span>Version {item.version}{item.isCurrent ? " · Live" : ""}<small>{new Date(item.publishedAt).toLocaleString()}</small></span>{!item.isCurrent ? <button className="secondary-button" type="button" disabled={status!=="ready"} onClick={()=>revert(item)}>Restore</button> : null}</li>)}</ul> : <p>Nothing has been published yet.</p>}</section>
    </aside><div className="phone-preview-wrap"><p className="preview-badge">Draft preview · real catalog</p><div className={`phone-preview template-${config.template}`} style={{"--preview-primary":config.colors.primary,"--preview-accent":config.colors.accent,"--preview-bg":config.colors.background,"--preview-surface":config.colors.surface,"--preview-text":config.colors.text}}><div className="phone-speaker"/><nav>{config.displayName}<span>Bag</span></nav><header><p>{config.tagline}</p><h2>{config.displayName}</h2><button>Start an order</button></header><main><h3>Popular today</h3><div className="preview-products">{sample.length?sample.map((p)=><article key={p.id}><div/><strong>{p.name}</strong><span>${Number(p.price).toFixed(2)}</span></article>):<p>Your real products will appear here.</p>}</div></main></div></div></div>
  </section>;
}
