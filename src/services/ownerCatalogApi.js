const OWNER_CATALOG_PATH = "/api/v1/owner/catalog";
const OWNER_CATALOG_CACHE_MS = 30_000;

let cachedOwnerCatalog = null;
let cachedOwnerCatalogExpiresAt = 0;
let pendingOwnerCatalog = null;

export class OwnerCatalogError extends Error {
  constructor(message, { status } = {}) {
    super(message);
    this.name = "OwnerCatalogError";
    this.status = status;
  }
}

async function request(path = "", {
  apiBaseUrl = import.meta.env?.VITE_API_BASE_URL || "",
  body,
  csrfToken,
  fetchImpl = globalThis.fetch,
  method = "GET",
} = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  let response;
  try {
    response = await fetchImpl(
      `${apiBaseUrl.replace(/\/+$/, "")}${OWNER_CATALOG_PATH}${path}`,
      {
        body: body === undefined ? undefined : JSON.stringify(body),
        credentials: "include",
        headers,
        method,
      }
    );
  } catch (cause) {
    throw new OwnerCatalogError("Unable to reach the production catalog.", { cause });
  }
  if (response.status === 204) return null;
  let payload = null;
  try { payload = await response.json(); } catch { /* normalized below */ }
  if (!response.ok) {
    const detail = payload?.detail;
    throw new OwnerCatalogError(
      (typeof detail === "object" ? detail?.message : detail) || "Catalog update failed.",
      { status: response.status }
    );
  }
  return payload;
}

export function fetchOwnerCatalog(options = {}) {
  return request("", options);
}

export function clearOwnerCatalogCache() {
  cachedOwnerCatalog = null;
  cachedOwnerCatalogExpiresAt = 0;
}

export function fetchOwnerCatalogCached({ force = false, ...options } = {}) {
  const now = Date.now();
  if (!force && cachedOwnerCatalog && now < cachedOwnerCatalogExpiresAt) {
    return Promise.resolve(cachedOwnerCatalog);
  }
  if (!force && pendingOwnerCatalog) return pendingOwnerCatalog;
  pendingOwnerCatalog = fetchOwnerCatalog(options)
    .then((catalog) => {
      cachedOwnerCatalog = catalog;
      cachedOwnerCatalogExpiresAt = Date.now() + OWNER_CATALOG_CACHE_MS;
      return catalog;
    })
    .finally(() => { pendingOwnerCatalog = null; });
  return pendingOwnerCatalog;
}

export function createOwnerProduct(product, csrfToken, options = {}) {
  return request("/products", { ...options, body: product, csrfToken, method: "POST" });
}

export function updateOwnerProduct(productId, product, csrfToken, options = {}) {
  return request(`/products/${encodeURIComponent(productId)}`, {
    ...options, body: product, csrfToken, method: "PUT",
  });
}

export function createOwnerModifierGroup(group, csrfToken, options = {}) {
  return request("/modifier-groups", { ...options, body: group, csrfToken, method: "POST" });
}

export function updateOwnerModifierGroup(groupId, group, csrfToken, options = {}) {
  return request(`/modifier-groups/${encodeURIComponent(groupId)}`, {
    ...options, body: group, csrfToken, method: "PUT",
  });
}

export function createOwnerModifierOption(groupId, option, csrfToken, options = {}) {
  return request(`/modifier-groups/${encodeURIComponent(groupId)}/options`, {
    ...options, body: option, csrfToken, method: "POST",
  });
}

export function updateOwnerModifierOption(groupId, optionId, option, csrfToken, options = {}) {
  return request(`/modifier-groups/${encodeURIComponent(groupId)}/options/${encodeURIComponent(optionId)}`, {
    ...options, body: option, csrfToken, method: "PUT",
  });
}

export async function saveOwnerCustomization({ groupId, group, choices }, csrfToken, options = {}) {
  let savedGroup = null;
  const savedChoices = [];
  try {
    savedGroup = groupId
      ? await updateOwnerModifierGroup(groupId, group, csrfToken, options)
      : await createOwnerModifierGroup(group, csrfToken, options);
    const savedGroupId = savedGroup?.id || groupId;
    for (const [index, choice] of choices.entries()) {
      const response = choice.optionId
        ? await updateOwnerModifierOption(savedGroupId, choice.optionId, choice.payload, csrfToken, options)
        : await createOwnerModifierOption(savedGroupId, choice.payload, csrfToken, options);
      savedChoices.push({ clientId: choice.clientId, index, response });
    }
    return { group: savedGroup, choices: savedChoices };
  } catch (error) {
    error.partialCustomization = { group: savedGroup, choices: savedChoices };
    if (savedGroup) {
      error.message = `${group.name} was saved, but not every choice was saved. Review the choices below and try again.`;
    }
    throw error;
  }
}

export function archiveOwnerProduct(productId, csrfToken, options = {}) {
  return request(`/products/${encodeURIComponent(productId)}`, {
    ...options, csrfToken, method: "DELETE",
  });
}

export function updateOwnerProductAvailability(productId, available, csrfToken, options = {}) {
  return request(`/products/${encodeURIComponent(productId)}/availability`, {
    ...options, body: { available }, csrfToken, method: "PATCH",
  });
}

export function updateLunchSpecial(productId, csrfToken, options = {}) {
  return request("/lunch-special", {
    ...options, body: { product_id: productId }, csrfToken, method: "PUT",
  });
}
