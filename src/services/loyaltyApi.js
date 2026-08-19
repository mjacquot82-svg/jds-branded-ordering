const apiRoot = () => (import.meta.env?.VITE_API_BASE_URL || "").replace(/\/+$/, "");

async function request(path, { method="GET", body, csrfToken, fetchImpl=globalThis.fetch, apiBaseUrl=apiRoot() }={}) {
  const response = await fetchImpl(`${apiBaseUrl.replace(/\/+$/, "")}/api/v1${path}`, { method, credentials:"include", cache:method==="GET"?"no-store":undefined, headers:{Accept:"application/json",...(body!==undefined?{"Content-Type":"application/json"}:{}),...(csrfToken?{"X-CSRF-Token":csrfToken}:{})}, body:body===undefined?undefined:JSON.stringify(body) });
  let payload=null; try { payload=await response.json(); } catch {}
  if(!response.ok) throw new Error(payload?.detail?.message || "Loyalty could not be updated.");
  return payload;
}

export const fetchCustomerLoyalty=(options={})=>request("/customer/loyalty",options);
export const fetchOwnerLoyalty=(options={})=>request("/owner/loyalty",options);
export const saveLoyaltyProgram=(program,csrfToken,options={})=>request("/owner/loyalty/program",{...options,method:"PUT",body:program,csrfToken});
export const searchLoyaltyCustomers=(query,options={})=>request(`/owner/loyalty/customers?q=${encodeURIComponent(query)}`,options);
export const adjustCustomerLoyalty=(adjustment,csrfToken,options={})=>request("/owner/loyalty/adjustments",{...options,method:"POST",body:adjustment,csrfToken});
