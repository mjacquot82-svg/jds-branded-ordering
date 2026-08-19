const CATALOG_PATH = "/api/v1/catalog";

export class CatalogApiError extends Error {
  constructor(message, { cause, status } = {}) {
    super(message, { cause });
    this.name = "CatalogApiError";
    this.status = status;
  }
}

export async function fetchCatalog({
  apiBaseUrl = import.meta.env?.VITE_API_BASE_URL || "",
  fetchImpl = globalThis.fetch,
  signal,
} = {}) {
  if (typeof fetchImpl !== "function") {
    throw new CatalogApiError("Catalog requests are unavailable.");
  }

  const url = `${apiBaseUrl.replace(/\/+$/, "")}${CATALOG_PATH}`;
  let response;

  try {
    response = await fetchImpl(url, {
      headers: { Accept: "application/json" },
      method: "GET",
      signal,
    });
  } catch (cause) {
    throw new CatalogApiError("Unable to reach the catalog service.", { cause });
  }

  if (!response.ok) {
    throw new CatalogApiError("The catalog service returned an error.", {
      status: response.status,
    });
  }

  let payload;
  try {
    payload = await response.json();
  } catch (cause) {
    throw new CatalogApiError("The catalog service returned invalid JSON.", {
      cause,
      status: response.status,
    });
  }

  if (
    !payload ||
    typeof payload !== "object" ||
    typeof payload.version !== "string" ||
    !payload.pricing ||
    typeof payload.pricing !== "object" ||
    !Array.isArray(payload.categories)
  ) {
    throw new CatalogApiError("The catalog response has an invalid shape.", {
      status: response.status,
    });
  }

  return payload;
}
