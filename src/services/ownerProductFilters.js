export function visibleProducts(products, { category = "all", query = "", status = "all" } = {}) {
  const term = query.trim().toLocaleLowerCase();
  return products.filter((product) => {
    const state = !product.published ? "hidden" : product.available ? "available" : "unavailable";
    return (category === "all" || product.category === category)
      && (status === "all" || state === status)
      && (!term || `${product.name} ${product.description}`.toLocaleLowerCase().includes(term));
  }).sort((left, right) => left.name.localeCompare(right.name));
}
