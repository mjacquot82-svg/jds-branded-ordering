const PATH = "/api/v1/owner/communications";

export class OwnerCommunicationsError extends Error {
  constructor(message, { cause, code, status } = {}) {
    super(message, { cause });
    this.name = "OwnerCommunicationsError";
    this.code = code;
    this.status = status;
  }
}

export async function fetchOwnerCommunications({
  apiBaseUrl = import.meta.env?.VITE_API_BASE_URL || "",
  fetchImpl = globalThis.fetch,
  signal,
} = {}) {
  let response;
  try {
    response = await fetchImpl(`${apiBaseUrl.replace(/\/+$/, "")}${PATH}`, {
      credentials: "include",
      headers: { Accept: "application/json" },
      signal,
    });
  } catch (cause) {
    throw new OwnerCommunicationsError("Unable to reach communications.", { cause });
  }
  let payload;
  try { payload = await response.json(); } catch (cause) {
    throw new OwnerCommunicationsError("Communications returned an invalid response.", { cause, status: response.status });
  }
  if (!response.ok) {
    throw new OwnerCommunicationsError(payload?.detail?.message || "Communication status could not be loaded.", {
      code: payload?.detail?.code,
      status: response.status,
    });
  }
  return payload;
}

async function send(path, body, csrfToken, {fetchImpl=globalThis.fetch,apiBaseUrl=import.meta.env?.VITE_API_BASE_URL||""}={}) {
  const response=await fetchImpl(`${apiBaseUrl.replace(/\/+$/,"")}${PATH}${path}`,{method:"POST",credentials:"include",headers:{Accept:"application/json","Content-Type":"application/json","X-CSRF-Token":csrfToken,"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify(body)});
  let payload={};try{payload=await response.json()}catch{}
  if(!response.ok)throw new OwnerCommunicationsError(payload?.detail?.message||"Announcement could not be queued.",{code:payload?.detail?.code,status:response.status});
  return payload;
}
export const sendLunchSpecial=(csrfToken,{override=false,confirmOverride=false}={})=>send("/lunch-special",{kind:"lunch_special",override,confirm_override:confirmOverride},csrfToken);
export const sendGeneralAnnouncement=(csrfToken,{title,body,targetRoute})=>send("/general",{title,body,target_route:targetRoute},csrfToken);
