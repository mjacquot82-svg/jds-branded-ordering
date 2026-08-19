import { useEffect, useState } from "react";
import { fetchPlatformOrganizations } from "../services/designStudioApi.js";

export default function PlatformAdminPage() {
  const [organizations,setOrganizations]=useState(null); const [error,setError]=useState("");
  useEffect(()=>{fetchPlatformOrganizations().then(setOrganizations).catch((reason)=>setError(reason.message));},[]);
  return <section className="page-section platform-admin"><header><p className="eyebrow">JDS platform</p><h1>Organizations</h1><p>Operational status only. Customer details and credentials are not shown.</p></header>
    {error?<div className="owner-page-message error"><strong>Platform access is restricted.</strong><p>{error}</p></div>:organizations===null?<p>Loading organization health…</p>:organizations.length===0?<p>No organizations have been provisioned.</p>:<div className="platform-table-wrap"><table><thead><tr><th>Business</th><th>Storefront</th><th>Readiness</th><th>Clover</th><th>Design</th><th>Subscription</th></tr></thead><tbody>{organizations.map((item)=><tr key={item.id}><td><strong>{item.name}</strong><small>{item.ownerMemberships} owner membership{item.ownerMemberships===1?"":"s"}</small></td><td>{item.canonicalHost||"Not verified"}</td><td>{item.publicReady?"Public ready":item.onboarding.replaceAll("_"," ")}</td><td>{item.cloverHealth.join(", ").replaceAll("_"," ")}</td><td>{item.publishedVersionId?"Published":"Not published"}</td><td>{item.subscription.replaceAll("_"," ")}</td></tr>)}</tbody></table></div>}
  </section>;
}
