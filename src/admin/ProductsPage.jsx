import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Check, Plus, Search, SlidersHorizontal, Trash2 } from "lucide-react";
import { createProductId, useCatalogProducts } from "../stores/catalogStore.js";
import { visibleProducts } from "../services/ownerProductFilters.js";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { canEditProducts, canManageLunchSpecial, canManageProductAvailability } from "../auth/ownerProductPermissions.js";
import ModifierManager from "./ModifierManager.jsx";
import { isProductDraftDirty } from "./productDraft.js";

const emptyProduct = { id: "", name: "", description: "", price: "", category: "", image: "", available: true, published: true, featured: false, lunchSpecial: false, variants: [], modifierGroupIds: [] };
const money = (price) => new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(price);
const toFormProduct = (product) => ({ ...emptyProduct, ...product, price: String(product.price ?? ""), variants: (product.variants || []).map((variant) => ({ ...variant, price: (variant.price_cents / 100).toFixed(2) })), modifierGroupIds: product.modifierGroupIds || [] });
const variantKey = () => `variant-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

export default function ProductsPage() {
  const { session } = useOwnerAuth();
  const canEdit = canEditProducts(session);
  const canManageAvailability = canManageProductAvailability(session);
  const canManageSpecial = canManageLunchSpecial(session);
  const navigate = useNavigate();
  const location = useLocation();
  const { products, categories, modifierGroups, addProduct, updateProduct, setProductAvailability, setLunchSpecial, saveCustomization, loading, error } = useCatalogProducts();
  const [managingModifiers, setManagingModifiers] = useState(false);
  const [selectedProductId, setSelectedProductId] = useState("");
  const [formProduct, setFormProduct] = useState(emptyProduct);
  const [savedProduct, setSavedProduct] = useState(emptyProduct);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [saving, setSaving] = useState(false);
  const [availabilityBusy, setAvailabilityBusy] = useState("");
  const [lunchSpecialBusy, setLunchSpecialBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [leaveOpen, setLeaveOpen] = useState(false);
  const dialogRef = useRef(null);
  const pendingLeaveRef = useRef(null);
  const allowNavigationRef = useRef(false);
  const savingRef = useRef(false);
  const selectedProduct = useMemo(() => products.find((product) => product.id === selectedProductId), [products, selectedProductId]);
  const filtered = useMemo(() => visibleProducts(products, { category, query, status: statusFilter }), [products, category, query, statusFilter]);
  const dirty = isProductDraftDirty(formProduct, savedProduct, categories[0]?.id || "");
  const updateField = (field, value) => setFormProduct((current) => ({ ...current, [field]: value }));
  const resetForm = useCallback(() => { const next = { ...emptyProduct, category: categories[0]?.id || "" }; setSelectedProductId(""); setFormProduct(next); setSavedProduct(next); }, [categories]);
  const startEdit = useCallback((product) => { const next = toFormProduct(product); setSelectedProductId(product.id); setFormProduct(next); setSavedProduct(next); setNotice(""); window.scrollTo?.({ top: 0, behavior: "smooth" }); }, []);
  const requestLeave = useCallback((action, navigation = false) => { pendingLeaveRef.current = { action, navigation }; setLeaveOpen(true); }, []);
  const requestProductAction = useCallback((action) => { if (dirty) requestLeave(action); else action(); }, [dirty, requestLeave]);
  useEffect(() => { const dialog = dialogRef.current; if (leaveOpen && !dialog?.open) dialog?.showModal(); if (!leaveOpen && dialog?.open) dialog.close(); }, [leaveOpen]);
  useEffect(() => { if (!dirty) return; const beforeUnload = (event) => { if (allowNavigationRef.current) return; event.preventDefault(); event.returnValue = ""; }; window.addEventListener("beforeunload", beforeUnload); return () => window.removeEventListener("beforeunload", beforeUnload); }, [dirty]);
  useEffect(() => {
    if (!dirty) return;
    const currentPath = location.pathname;
    const navigationApi = window.navigation;
    if (navigationApi?.addEventListener) {
      const onNavigate = (event) => { if (allowNavigationRef.current || !event.canIntercept || event.hashChange) return; const destination = new URL(event.destination.url); if (destination.origin !== window.location.origin || destination.pathname === currentPath) return; event.preventDefault(); const key = event.destination.key; requestLeave(() => key && navigationApi.entries().some((entry) => entry.key === key) ? navigationApi.traverseTo(key) : navigate(`${destination.pathname}${destination.search}${destination.hash}`), true); };
      navigationApi.addEventListener("navigate", onNavigate); return () => navigationApi.removeEventListener("navigate", onNavigate);
    }
    const onClick = (event) => { if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return; const anchor = event.target.closest?.("a[href]"); if (!anchor || anchor.target && anchor.target !== "_self" || anchor.hasAttribute("download")) return; const destination = new URL(anchor.href, window.location.href); if (destination.origin !== window.location.origin || destination.pathname === currentPath) return; event.preventDefault(); event.stopPropagation(); requestLeave(() => navigate(`${destination.pathname}${destination.search}${destination.hash}`), true); };
    document.addEventListener("click", onClick, true); return () => document.removeEventListener("click", onClick, true);
  }, [dirty, location.pathname, navigate, requestLeave]);
  function stay(event) { event?.preventDefault(); pendingLeaveRef.current = null; setLeaveOpen(false); }
  function leaveWithoutSaving() { const pending = pendingLeaveRef.current; if (pending?.navigation) allowNavigationRef.current = true; pendingLeaveRef.current = null; setLeaveOpen(false); pending?.action?.(); }
  function toggleModifierGroup(groupId) { setFormProduct((current) => ({ ...current, modifierGroupIds: current.modifierGroupIds.includes(groupId) ? current.modifierGroupIds.filter((id) => id !== groupId) : [...current.modifierGroupIds, groupId] })); }
  function addVariant() { setFormProduct((current) => ({ ...current, variants: [...current.variants, { key: variantKey(), name: "", price: current.price || "", active: true, sort_order: current.variants.length }] })); }
  function updateVariant(index, field, value) { setFormProduct((current) => ({ ...current, variants: current.variants.map((variant, variantIndex) => variantIndex === index ? { ...variant, [field]: value } : variant) })); }
  function removeNewVariant(index) { setFormProduct((current) => ({ ...current, variants: current.variants.filter((_, variantIndex) => variantIndex !== index).map((variant, sortOrder) => ({ ...variant, sort_order: sortOrder })) })); }

  async function toggleAvailability(product) {
    if (availabilityBusy) return;
    const next = !product.available;
    setAvailabilityBusy(product.id); setNotice("");
    try {
      await setProductAvailability(product.id, next);
      setNotice(next ? `${product.name} is available for online ordering.` : `${product.name} is unavailable for online ordering.`);
    } catch (nextError) { setNotice(nextError.message); }
    finally { setAvailabilityBusy(""); }
  }

  async function changeLunchSpecial(product) {
    if (lunchSpecialBusy) return;
    setLunchSpecialBusy(true); setNotice("");
    try {
      await setLunchSpecial(product.lunchSpecial ? null : product.id);
      setNotice(product.lunchSpecial ? "Lunch Special cleared." : `${product.name} is now the Lunch Special.`);
    } catch (nextError) { setNotice(nextError.message); }
    finally { setLunchSpecialBusy(false); }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (saving) return;
    if (savingRef.current) return;
    const productId = selectedProductId || createProductId(formProduct.name);
    const variants = formProduct.variants.map((variant, index) => ({ ...variant, name: variant.name.trim(), price_cents: Math.round(Number(variant.price) * 100), sort_order: index }));
    const payload = { ...formProduct, id: productId, name: formProduct.name.trim(), description: formProduct.description.trim(), price: Number(formProduct.price), category: formProduct.category || categories[0]?.id, variants };
    if (!payload.name || !Number.isFinite(payload.price) || payload.price < 0 || !payload.category) { setNotice("Add a name, category, and valid price."); return; }
    if (variants.some((variant) => !variant.name || !Number.isFinite(variant.price_cents) || variant.price_cents < 0)) { setNotice("Every variant needs a name and valid price."); return; }
    savingRef.current = true; setSaving(true); setNotice("");
    try {
      if (selectedProduct) await updateProduct(selectedProduct.id, payload);
      else await addProduct({ ...payload, id: products.some((item) => item.id === productId) ? `${productId}-${Date.now()}` : productId });
      setNotice(`${payload.name} saved.`); resetForm();
    } catch (nextError) { setNotice(nextError.message); }
    finally { savingRef.current = false; setSaving(false); }
  }

  if (canEdit && managingModifiers) return <ModifierManager groups={modifierGroups} onClose={() => setManagingModifiers(false)} onSaveCustomization={saveCustomization} />;

  return <section className="page-section admin-products-page">
    <div className="page-heading admin-page-heading"><div><p className="eyebrow">Product catalog</p><h1>Products</h1><p>{canEdit ? "Find an item, mark it sold out, or make a quick change." : "Find an item, update availability, or set today’s Lunch Special."}</p></div>{canEdit ? <div className="admin-heading-actions"><button className="secondary-button admin-reset-button" type="button" onClick={() => requestProductAction(resetForm)}>Add product</button></div> : null}</div>
    {canEdit ? <nav className="products-view-switch" aria-label="Products sections"><button aria-current="page" className="is-active" type="button">Menu items</button><button type="button" onClick={() => requestProductAction(() => { resetForm(); setManagingModifiers(true); })}>Modifiers</button></nav> : null}
    {notice ? <div className="product-notice" role="status" aria-live="polite"><Check size={18} />{notice}</div> : null}
    {error ? <div className="product-notice error" role="alert">{error.message}</div> : null}

    <section className="product-quick-tools" aria-label="Find products">
      <label className="product-search"><Search aria-hidden="true" size={19} /><span className="sr-only">Search products</span><input type="search" placeholder="Search coffee, pastry…" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
      <label><SlidersHorizontal aria-hidden="true" size={18} /><span className="sr-only">Category</span><select aria-label="Filter by category" value={category} onChange={(event) => setCategory(event.target.value)}><option value="all">All categories</option>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label><span className="sr-only">Menu status</span><select aria-label="Filter by menu status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">All statuses</option><option value="available">Available for ordering</option><option value="unavailable">Unavailable for ordering</option><option value="hidden">Hidden from menu</option></select></label>
    </section>

    <div className={`admin-products-layout${canEdit ? "" : " availability-only"}`}>
      <section className="product-list-panel" aria-labelledby="product-list-heading"><div className="section-heading"><div><h2 id="product-list-heading">Menu items</h2><span>{loading ? "Loading menu…" : `${filtered.length} of ${products.length} products`}</span></div></div>
        {loading ? <div className="product-list-skeleton" aria-label="Loading products">{[1,2,3,4].map((item) => <span key={item} />)}</div> : filtered.length ? <div className="product-table">{filtered.map((product) => {
          const productCategory = categories.find((item) => item.id === product.category);
          const categoryName = productCategory?.name || product.category;
          const categoryVisible = productCategory?.published !== false;
          const state = !product.published ? "hidden" : product.available ? "available" : "unavailable";
          const canSelectSpecial = product.published && categoryVisible;
          return <article className={`product-row ${state}${product.lunchSpecial ? " lunch-special-current" : ""}`} key={product.id}><div className="product-row-copy"><strong>{product.name}</strong><span>{categoryName}{product.lunchSpecial ? " · Current Lunch Special" : ""}</span><p>{product.description || "No description"}</p></div><div className="product-row-meta"><strong>{money(product.price)}</strong><span className={`menu-state ${state}`}>{state === "unavailable" ? "Unavailable for ordering" : state === "available" ? "Available for ordering" : "Hidden from menu"}</span></div><div className="product-row-actions">{canManageAvailability ? <button className={product.available ? "sold-out-button" : "available-button"} disabled={availabilityBusy === product.id || !product.published} type="button" onClick={() => toggleAvailability(product)}>{availabilityBusy === product.id ? "Updating…" : product.available ? "Mark unavailable" : "Make available"}</button> : null}{canManageSpecial ? <button className={product.lunchSpecial ? "secondary-button" : "lunch-special-button"} disabled={lunchSpecialBusy || (!product.lunchSpecial && !canSelectSpecial)} title={!canSelectSpecial && !product.lunchSpecial ? "Only products visible on the customer menu can be selected." : undefined} type="button" onClick={() => changeLunchSpecial(product)}>{lunchSpecialBusy ? "Updating…" : product.lunchSpecial ? "Clear Lunch Special" : "Set as Lunch Special"}</button> : null}{canEdit ? <button type="button" onClick={() => requestProductAction(() => startEdit(product))}>Edit</button> : null}</div></article>;
        })}</div> : <div className="product-empty"><Search size={28} /><h3>No matching products</h3><p>Try another search or clear the filters.</p><button className="secondary-button" type="button" onClick={() => { setQuery(""); setCategory("all"); setStatusFilter("all"); }}>Clear filters</button></div>}
      </section>

      {canEdit ? <section className="product-editor-panel" aria-labelledby="product-editor-heading"><div className="section-heading"><div><p className="eyebrow">Product configuration</p><h2 id="product-editor-heading">{selectedProduct ? `Edit ${selectedProduct.name}` : "Create product"}</h2></div></div><form className="product-form" aria-busy={saving} onSubmit={handleSubmit}>
        <section className="product-editor-section" aria-labelledby="basic-information-heading"><div className="product-editor-section-heading"><h3 id="basic-information-heading">Basic information</h3><p>Describe the product and where customers can find it.</p></div>
          <label><span>Name</span><input required value={formProduct.name} onChange={(event) => updateField("name", event.target.value)} /></label>
          <label><span>Description</span><textarea rows="3" value={formProduct.description} onChange={(event) => updateField("description", event.target.value)} /></label>
          <div className="form-grid"><label><span>Base price</span><input min="0" required step="0.01" type="number" value={formProduct.price} onChange={(event) => updateField("price", event.target.value)} /><small>Used when this product has no available variants.</small></label><label><span>Category</span><select required value={formProduct.category || categories[0]?.id || ""} onChange={(event) => updateField("category", event.target.value)}>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div>
          <label><span>Image</span><input placeholder="Image URL or token" value={formProduct.image} onChange={(event) => updateField("image", event.target.value)} /></label>
        </section>
        <section className="product-editor-section product-variants" aria-labelledby="product-variants-heading"><div className="product-editor-section-heading"><h3 id="product-variants-heading">Variants</h3><p>Which version of this product is being purchased?</p></div>
          {formProduct.variants.length ? <div className="product-variant-list">{formProduct.variants.map((variant, index) => <div className={variant.active === false ? "product-variant-row is-unavailable" : "product-variant-row"} key={variant.id || variant.key}>
            <label><span>Variant</span><input aria-label={`Variant ${index + 1} name`} placeholder="For example, 16oz Iced" required value={variant.name} onChange={(event) => updateVariant(index, "name", event.target.value)} /></label>
            <label><span>Price</span><input aria-label={`${variant.name || `Variant ${index + 1}`} price`} min="0" required step="0.01" type="number" value={variant.price} onChange={(event) => updateVariant(index, "price", event.target.value)} /></label>
            {variant.id ? <label className="variant-available-toggle"><input checked={variant.active !== false} type="checkbox" onChange={(event) => updateVariant(index, "active", event.target.checked)} /><span>Available</span></label> : <button aria-label={`Remove variant ${index + 1}`} className="variant-remove-button" type="button" onClick={() => removeNewVariant(index)}><Trash2 aria-hidden="true" size={17} /> Remove</button>}
          </div>)}</div> : <div className="variant-empty-state"><strong>No variants added.</strong><p>Customers will order this product at its base price.</p></div>}
          <button className="secondary-button add-variant-button" type="button" onClick={addVariant}><Plus aria-hidden="true" size={17} /> Add variant</button>
        </section>
        <section className="product-editor-section product-modifiers" aria-labelledby="product-modifiers-heading"><div className="product-editor-section-heading"><h3 id="product-modifiers-heading">Modifiers</h3><p>What can the customer add or change? Choose which modifier categories are available on this product.</p></div>{modifierGroups.some((group) => group.active) ? <div className="product-modifier-options">{modifierGroups.filter((group) => group.active || formProduct.modifierGroupIds.includes(group.id)).map((group) => { const assigned = formProduct.modifierGroupIds.includes(group.id); const preview = group.options.filter((item) => item.active).map((item) => `${item.name}${item.priceAdjustmentCents ? ` +$${(item.priceAdjustmentCents / 100).toFixed(2)}` : ""}`).join(" · "); return <label className={assigned ? "is-selected" : ""} key={group.id}><input checked={assigned} disabled={!group.active && !assigned} type="checkbox" onChange={() => toggleModifierGroup(group.id)} /><span><strong>{group.name}</strong><small>{preview || "No available modifiers yet"}{group.active ? "" : " · Category unavailable"}</small><b>{assigned ? "Available on this product" : "Not available on this product"}</b></span></label>; })}</div> : <div className="modifier-assignment-empty"><strong>No modifiers have been created yet.</strong></div>}<button className="secondary-button" type="button" onClick={() => requestProductAction(() => { resetForm(); setManagingModifiers(true); })}>Manage modifiers</button></section>
        <section className="product-editor-section product-settings" aria-labelledby="product-settings-heading"><div className="product-editor-section-heading"><h3 id="product-settings-heading">Availability and placement</h3><p>Control where this product appears and whether it can be ordered.</p></div>
        <div className="product-state-controls" aria-label="Product visibility and placement">
          <label className={formProduct.available ? "product-state-toggle is-on" : "product-state-toggle"}><input checked={formProduct.available} type="checkbox" onChange={(event) => updateField("available", event.target.checked)} /><span aria-hidden="true" className="product-toggle-track" /><span><strong>Available for online ordering</strong><small>When visible, include it on the customer menu and allow ordering.</small></span></label>
          <label className={formProduct.published !== false ? "product-state-toggle is-on" : "product-state-toggle"}><input checked={formProduct.published !== false} type="checkbox" onChange={(event) => updateField("published", event.target.checked)} /><span aria-hidden="true" className="product-toggle-track" /><span><strong>Visible on customer menu</strong><small>Turn off to hide this product without archiving it.</small></span></label>
          <label className={formProduct.featured ? "product-state-toggle is-on" : "product-state-toggle"}><input checked={formProduct.featured} type="checkbox" onChange={(event) => updateField("featured", event.target.checked)} /><span aria-hidden="true" className="product-toggle-track" /><span><strong>Featured</strong><small>Highlight this product in customer recommendations.</small></span></label>
          <label className={formProduct.lunchSpecial ? "product-state-toggle is-on" : "product-state-toggle"}><input checked={formProduct.lunchSpecial} type="checkbox" onChange={(event) => updateField("lunchSpecial", event.target.checked)} /><span aria-hidden="true" className="product-toggle-track" /><span><strong>Lunch special</strong><small>Select as the current lunch special; choosing another product replaces it.</small></span></label>
        </div>
        </section>
        <div className="form-actions"><button className="primary-button" disabled={saving} type="submit">{saving ? "Saving…" : selectedProduct ? "Save changes" : "Add product"}</button>{selectedProduct ? <button className="secondary-button" type="button" onClick={() => requestProductAction(resetForm)}>Cancel</button> : null}</div>
      </form></section> : null}
    </div>
    <dialog aria-describedby="unsaved-product-message" aria-labelledby="unsaved-product-title" className="owner-confirm-dialog loyalty-unsaved-dialog" onCancel={stay} ref={dialogRef}><h2 id="unsaved-product-title">Unsaved product changes</h2><p id="unsaved-product-message">You have unsaved product changes. Leave without saving?</p><div className="form-actions"><button autoFocus className="secondary-button" type="button" onClick={stay}>Stay</button><button className="primary-button" type="button" onClick={leaveWithoutSaving}>Leave without saving</button></div></dialog>
  </section>;
}
