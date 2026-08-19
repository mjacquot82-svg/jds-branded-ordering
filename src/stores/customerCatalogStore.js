import { useEffect, useState } from "react";

import { createCatalogResource } from "../services/catalogResource.js";

export function createCustomerCatalogResource(options) {
  return createCatalogResource(options);
}

export const customerCatalogResource = createCustomerCatalogResource();

export function useCustomerCatalog() {
  const [state, setState] = useState(customerCatalogResource.getState);

  useEffect(() => customerCatalogResource.subscribe(setState), []);

  useEffect(() => {
    if (customerCatalogResource.getState().status === "idle") {
      customerCatalogResource.load();
    }
  }, []);

  return {
    ...state,
    reload: () => customerCatalogResource.load(),
  };
}
