import { useEffect,useState } from "react";
import { fetchCustomerLoyalty } from "../services/loyaltyApi.js";
import LoyaltyCard from "./LoyaltyCard.jsx";

export default function AccountLoyalty(){
 const [state,setState]=useState({loading:true,program:null,error:""});
 useEffect(()=>{fetchCustomerLoyalty().then(v=>setState({loading:false,program:v.programs?.[0]||null,error:""})).catch(e=>setState({loading:false,program:null,error:e.message}))},[]);
 if(state.loading)return <section id="loyalty" className="content-block"><p>Loading loyalty…</p></section>;
 return <section id="loyalty" className="account-loyalty-section">{state.error?<p className="form-status" role="alert">{state.error}</p>:<><LoyaltyCard compact program={state.program} signedIn/>{state.program?.activity?.length?<div className="loyalty-activity"><h3>Recent loyalty activity</h3>{state.program.activity.slice(0,5).map((item,index)=><p key={`${item.created_at}-${index}`}><span>{item.label}</span><time>{new Date(item.created_at).toLocaleDateString()}</time></p>)}</div>:null}</>}</section>;
}
