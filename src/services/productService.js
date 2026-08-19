import { createOwnerProduct, fetchOwnerCatalog, updateOwnerProduct } from "./ownerCatalogApi.js";

export async function getProducts() {
  return (await fetchOwnerCatalog()).products;
}

export async function saveProduct(product, csrfToken) {
  return product.backendId
    ? updateOwnerProduct(product.backendId, product, csrfToken)
    : createOwnerProduct(product, csrfToken);
}
