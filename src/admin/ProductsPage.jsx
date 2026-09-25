import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Check, Plus, Search, SlidersHorizontal, Trash2 } from "lucide-react";
import { createProductId, useCatalogProducts } from "../stores/catalogStore.js";
import { visibleProducts } from "../services/ownerProductFilters.js";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { canEditProducts, canManageLunchSpecial, canManageProductAvailability } from "../auth/ownerProductPermissions.js";
import ModifierManager from "./ModifierManager.jsx";
import { isProductDraftDirty } from "./productDraft.js";
import { imageRequirements } from "../design/imageRequirements.js";
import { inspectImageFile, validateProductImage } from "../design/imageRequirements.js";
import { archiveMedia, fetchMedia, fetchStarterMedia, uploadMedia } from "../services/designStudioApi.js";
import { fetchDemoStatus } from "../services/demoFunnelApi.js";
import { filterStarterMedia, ownerProductImageUrl, productImageSource, productImageSourceLabel, starterCategoryLabel, suggestedStarterMedia } from "../services/starterMedia.js";

const emptyProduct = { id: "", name: "", description: "", price: "", category: "", image: "", available: true, published: true, featured: false, lunchSpecial: false, variants: [], modifierGroupIds: [] };
const money = (price) => new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(price);
const toFormProduct = (product) => ({ ...emptyProduct, ...product, price: String(product.price ?? ""), variants: (product.variants || []).map((variant) => ({ ...variant, price: (variant.price_cents / 100).toFixed(2) })), modifierGroupIds: product.modifierGroupIds || [] });
const variantKey = () => `variant-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

function StarterImageGrid({ assets, selected = "", onSelect }) {
  return <div className="starter-image-grid">{assets.map((asset)=>{const isSelected=selected===asset.reference;return <button aria-pressed={isSelected} className={isSelected?"is-selected":""} disabled={!asset.available} key={asset.reference} type="button" onClick={()=>onSelect(asset)}>{asset.thumbnailUrl?<img alt="" loading="lazy" src={asset.thumbnailUrl}/>:<span className="starter-image-unavailable">Image coming soon</span>}<b>{asset.name}</b><small>{!asset.available?"Not yet available":isSelected?"Selected":"Use this image"}</small></button>;})}</div>;
}

const formatMegabytes = (bytes) => `${(Number(bytes || 0) / 1_000_000).toFixed(1).replace(/\.0$/, "")} MB`;

export default function ProductsPage({ setupMode = false, onCatalogChange, onDirtyChange }) {
  const { session } = useOwnerAuth();
  const canEdit = canEditProducts(session);
  const canManageAvailability = canManageProductAvailability(session);
  const canManageSpecial = canManageLunchSpecial(session);
  const navigate = useNavigate();
  const location = useLocation();
  const { products, categories, modifierGroups, addCategory, updateCategory, removeCategory, reorderCategories, addProduct, updateProduct, reorderProducts, removeProduct, setProductAvailability, setLunchSpecial, saveCustomization, loading, error } = useCatalogProducts();
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
  const [creating, setCreating] = useState(false);
  const [categoryName, setCategoryName] = useState("");
  const [editingCategoryId, setEditingCategoryId] = useState("");
  const [editingCategoryName, setEditingCategoryName] = useState("");
  const [categoryBusy, setCategoryBusy] = useState(false);
  const [media, setMedia] = useState([]);
  const [starterMedia, setStarterMedia] = useState([]);
  const [starterPickerOpen, setStarterPickerOpen] = useState(false);
  const [starterQuery, setStarterQuery] = useState("");
  const [starterCategory, setStarterCategory] = useState("all");
  const [imageLibraryOpen, setImageLibraryOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [imageFeedback, setImageFeedback] = useState({ status: "", message: "", fileName: "" });
  const [demoLimits, setDemoLimits] = useState(null);
  const [mediaUsage, setMediaUsage] = useState({ files: 0, bytes: 0 });
  const [removingMediaId, setRemovingMediaId] = useState("");
  const [leaveOpen, setLeaveOpen] = useState(false);
  const dialogRef = useRef(null);
  const pendingLeaveRef = useRef(null);
  const allowNavigationRef = useRef(false);
  const savingRef = useRef(false);
  const editorRef = useRef(null);
  const nameRef = useRef(null);
  const selectedProduct = useMemo(() => products.find((product) => product.id === selectedProductId), [products, selectedProductId]);
  const filtered = useMemo(() => visibleProducts(products, { category, query, status: statusFilter }), [products, category, query, statusFilter]);
  const dirty = isProductDraftDirty(formProduct, savedProduct, categories[0]?.id || "");
  // Only starter images with shipped artwork are offered; manifest-only archetypes stay hidden.
  const availableStarterMedia = useMemo(() => starterMedia.filter((asset) => asset.available), [starterMedia]);
  const starterSuggestions = useMemo(() => suggestedStarterMedia(availableStarterMedia, formProduct.name), [availableStarterMedia, formProduct.name]);
  const visibleStarterMedia = useMemo(() => filterStarterMedia(availableStarterMedia, { category: starterCategory, query: starterQuery }), [availableStarterMedia, starterCategory, starterQuery]);
  const starterCategories = useMemo(() => [...new Set(availableStarterMedia.map((asset) => asset.category))], [availableStarterMedia]);
  const maxUploadLabel = demoLimits ? `${formatMegabytes(demoLimits.maxImageBytes)} (free demo)` : "10 MB";
  useEffect(() => { onDirtyChange?.(dirty); return () => onDirtyChange?.(false); }, [dirty, onDirtyChange]);
  const updateField = (field, value) => setFormProduct((current) => ({ ...current, [field]: value }));
  const resetForm = useCallback(() => { const next = { ...emptyProduct, category: categories[0]?.id || "" }; setSelectedProductId(""); setFormProduct(next); setSavedProduct(next); setCreating(false); setImageFeedback({ status: "", message: "", fileName: "" }); }, [categories]);
  const startCreate = useCallback((categoryId = categories[0]?.id || "") => { const next = { ...emptyProduct, category: categoryId }; setSelectedProductId(""); setFormProduct(next); setSavedProduct(next); setCreating(true); setNotice(""); setImageFeedback({ status: "", message: "", fileName: "" }); requestAnimationFrame(() => { editorRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" }); nameRef.current?.focus?.(); }); }, [categories]);
  const startEdit = useCallback((product) => { const next = toFormProduct(product); setSelectedProductId(product.id); setFormProduct(next); setSavedProduct(next); setNotice(""); setImageFeedback({ status: "", message: "", fileName: "" }); window.scrollTo?.({ top: 0, behavior: "smooth" }); }, []);
  const requestLeave = useCallback((action, navigation = false) => { pendingLeaveRef.current = { action, navigation }; setLeaveOpen(true); }, []);
  const requestProductAction = useCallback((action) => { if (dirty) requestLeave(action); else action(); }, [dirty, requestLeave]);
  useEffect(() => { const dialog = dialogRef.current; if (leaveOpen && !dialog?.open) dialog?.showModal(); if (!leaveOpen && dialog?.open) dialog.close(); }, [leaveOpen]);
  useEffect(() => {
    fetchMedia().then((items)=>{setMediaUsage({ files: items.length, bytes: items.reduce((total, asset) => total + Number(asset.byteSize || 0), 0) });setMedia(items.filter((asset)=>imageRequirements.product.formats.includes(asset.mediaType)&&asset.width>=800&&asset.height>=800));}).catch(() => {});
    fetchDemoStatus().then((status)=>setDemoLimits(status?.isProspect ? status.limits || null : null)).catch(() => setDemoLimits(null));
    fetchStarterMedia().then((payload)=>setStarterMedia(payload.assets || [])).catch(() => setStarterMedia([]));
  }, []);
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

  function createCategory(event) {
    event.preventDefault();
    if (dirty) { requestLeave(performCreateCategory); return; }
    performCreateCategory();
  }
  async function performCreateCategory() {
    const name = categoryName.trim();
    if (!name || categoryBusy) return;
    setCategoryBusy(true); setNotice("");
    try { const created = await addCategory(name); setCategoryName(""); setNotice(`${name} created. Now add its first product.`); startCreate(created.slug); onCatalogChange?.(); }
    catch (nextError) { setNotice(nextError.message); }
    finally { setCategoryBusy(false); }
  }
  async function saveCategory(categoryItem) {
    const name = editingCategoryName.trim(); if (!name) return;
    setCategoryBusy(true);
    try { await updateCategory(categoryItem.id, { name }); setEditingCategoryId(""); setNotice(`${name} saved.`); onCatalogChange?.(); }
    catch (nextError) { setNotice(nextError.message); }
    finally { setCategoryBusy(false); }
  }
  async function toggleCategory(categoryItem) {
    setCategoryBusy(true);
    try { await updateCategory(categoryItem.id, { published: !categoryItem.published }); setNotice(`${categoryItem.name} is now ${categoryItem.published ? "hidden from" : "visible on"} the customer menu.`); onCatalogChange?.(); }
    catch (nextError) { setNotice(nextError.message); }
    finally { setCategoryBusy(false); }
  }
  async function deleteCategory(categoryItem) {
    setCategoryBusy(true);
    try { await removeCategory(categoryItem.id); setNotice(`${categoryItem.name} deleted.`); onCatalogChange?.(); }
    catch (nextError) { setNotice(nextError.message); }
    finally { setCategoryBusy(false); }
  }
  async function moveCategory(index, direction) {
    const next = [...categories]; const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    try { await reorderCategories(next.map((item) => item.id)); onCatalogChange?.(); }
    catch (nextError) { setNotice(nextError.message); }
  }
  async function moveProduct(product, direction) {
    const sameCategory = products.filter((item) => item.category === product.category);
    const index = sameCategory.findIndex((item) => item.id === product.id); const target = index + direction;
    if (target < 0 || target >= sameCategory.length) return;
    const next = [...products]; const left = next.findIndex((item) => item.id === sameCategory[index].id); const right = next.findIndex((item) => item.id === sameCategory[target].id);
    [next[left], next[right]] = [next[right], next[left]];
    try { await reorderProducts(next.map((item) => item.id)); onCatalogChange?.(); }
    catch (nextError) { setNotice(nextError.message); }
  }
  async function uploadProductImage(event) {
    const file = event.target.files?.[0]; if (!file) return;
    if (uploading) return;
    setUploading(true); setNotice(""); setImageFeedback({ status: "busy", message: "Checking image…", fileName: file.name });
    try {
      const details = await inspectImageFile(file);
      const validation = validateProductImage(details);
      if (validation.errors.length) {
        setImageFeedback({ status: "error", message: validation.errors[0], fileName: file.name });
        return;
      }
      if (demoLimits?.maxImageBytes && file.size > demoLimits.maxImageBytes) {
        setImageFeedback({ status: "error", message: `This photo is larger than ${formatMegabytes(demoLimits.maxImageBytes)}, the free demo limit per photo. Try a smaller or compressed JPEG or WebP.`, fileName: file.name });
        return;
      }
      setImageFeedback({ status: "busy", message: "Uploading product image…", fileName: file.name });
      const asset = await uploadMedia(file, `${formProduct.name || "Product"} image`, session.csrf_token, "product");
      setMedia((items) => [asset, ...items.filter((item) => item.id !== asset.id)]);
      setMediaUsage((usage) => ({ files: usage.files + 1, bytes: usage.bytes + Number(asset.byteSize || 0) }));
      updateField("image", asset.url);
      setImageFeedback({ status: validation.warnings.length ? "warning" : "success", message: validation.warnings.length ? `Product image uploaded. ${validation.warnings[0]}` : "Product image uploaded.", fileName: file.name });
    }
    catch (nextError) { setImageFeedback({ status: "error", message: `${nextError.message || "Product image could not be uploaded."} Try again.`, fileName: file.name }); }
    finally { setUploading(false); event.target.value = ""; }
  }

  function chooseProductImage(asset) {
    updateField("image", asset.url);
    setImageFeedback({ status: "success", message: "Product image selected from your images.", fileName: asset.altText || "Library image" });
  }

  function chooseStarterImage(asset) {
    if (!asset.available) return;
    const replacedUpload = productImageSource(formProduct.image) === "upload";
    updateField("image", asset.reference);
    setImageFeedback({ status: "success", message: replacedUpload ? "JDS starter image selected. Your uploaded photo stays in My images until you delete it." : "JDS starter image selected.", fileName: asset.name });
    setStarterPickerOpen(false);
  }

  // Frees demo allowance via the existing tenant-scoped archive endpoint. The server
  // refuses images still used by a product or design, so nothing in use is lost.
  async function removeUnusedImage(asset) {
    if (removingMediaId) return;
    if (!globalThis.confirm?.("Delete this unused photo from your images? It will no longer count toward your photo allowance.")) return;
    setRemovingMediaId(asset.id);
    try {
      await archiveMedia(asset.id, session.csrf_token);
      setMedia((items) => items.filter((item) => item.id !== asset.id));
      setMediaUsage((usage) => ({ files: Math.max(0, usage.files - 1), bytes: Math.max(0, usage.bytes - Number(asset.byteSize || 0)) }));
      setImageFeedback({ status: "success", message: "Unused photo deleted.", fileName: asset.altText || "Uploaded image" });
    }
    catch (nextError) { setImageFeedback({ status: "error", message: nextError.message || "This photo could not be deleted.", fileName: asset.altText || "Uploaded image" }); }
    finally { setRemovingMediaId(""); }
  }

  function removeProductImage() {
    updateField("image", "");
    setImageFeedback({ status: "", message: "Product image removed from this draft.", fileName: "" });
  }

  async function toggleAvailability(product) {
    if (availabilityBusy) return;
    const next = !product.available;
    setAvailabilityBusy(product.id); setNotice("");
    try {
      await setProductAvailability(product.id, next);
      setNotice(next ? `${product.name} is available for online ordering.` : `${product.name} is unavailable for online ordering.`);
      onCatalogChange?.();
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
      setNotice(`${payload.name} saved.`); resetForm(); onCatalogChange?.();
    } catch (nextError) { setNotice(nextError.message); }
    finally { savingRef.current = false; setSaving(false); }
  }

  if (canEdit && managingModifiers) return <ModifierManager groups={modifierGroups} onClose={() => setManagingModifiers(false)} onSaveCustomization={saveCustomization} returnLabel={dirty ? `Back to ${formProduct.name.trim() || "product"} draft` : "Menu items"} />;

  return <section className={`page-section admin-products-page ${setupMode?"embedded-menu-step":""}`}>
    <div className="page-heading admin-page-heading"><div><p className="eyebrow">{setupMode?"Step 4":"Product catalog"}</p><h1>{setupMode?"Build your menu":"Products"}</h1><p>{setupMode?"Start by creating a category, then add the first item customers can order.":canEdit ? "Organize categories, products, prices, options, and availability." : "Find an item, update availability, or set today’s Lunch Special."}</p></div>{canEdit && categories.length ? <div className="admin-heading-actions"><button className="secondary-button admin-reset-button" type="button" onClick={() => requestProductAction(() => startCreate())}>Add product</button></div> : null}</div>
    {canEdit ? <nav className="products-view-switch" aria-label="Products sections"><button aria-current="page" className="is-active" type="button">Menu items</button><button type="button" onClick={() => setManagingModifiers(true)}>Modifiers</button></nav> : null}
    {notice ? <div className="product-notice" role="status" aria-live="polite"><Check size={18} />{notice}</div> : null}
    {error ? <div className="product-notice error" role="alert">{error.message}</div> : null}

    {canEdit ? <section className="catalog-category-manager" aria-labelledby="category-manager-heading"><div className="section-heading"><div><h2 id="category-manager-heading">Categories</h2><span>Organize how customers browse your menu.</span></div></div>
      {!categories.length ? <div className="category-first-state"><h3>{setupMode ? "Create your first category" : "This catalog needs a category"}</h3><p>{setupMode ? "Start with a group such as Coffee, Breakfast, Bakery, Lunch, or Drinks." : "Create a category before adding products."}</p></div> : <div className="category-management-list">{categories.map((item,index)=><article className={item.published ? "" : "is-hidden"} key={item.id}>{editingCategoryId===item.id?<><input aria-label="Category name" value={editingCategoryName} onChange={(event)=>setEditingCategoryName(event.target.value)}/><button type="button" disabled={categoryBusy} onClick={()=>saveCategory(item)}>Save</button><button type="button" onClick={()=>setEditingCategoryId("")}>Cancel</button></>:<><span><strong>{item.name}</strong><small>{item.published?"Visible to customers":"Hidden from customers"}</small></span><button type="button" onClick={()=>{setEditingCategoryId(item.id);setEditingCategoryName(item.name);}}>Rename</button><button type="button" disabled={categoryBusy} onClick={()=>requestProductAction(()=>toggleCategory(item))}>{item.published?"Hide":"Show"}</button><button aria-label={`Move ${item.name} up`} type="button" disabled={index===0||categoryBusy} onClick={()=>requestProductAction(()=>moveCategory(index,-1))}>Move up</button><button aria-label={`Move ${item.name} down`} type="button" disabled={index===categories.length-1||categoryBusy} onClick={()=>requestProductAction(()=>moveCategory(index,1))}>Move down</button><button type="button" disabled={categoryBusy} onClick={()=>requestProductAction(()=>deleteCategory(item))}>Delete</button></>}</article>)}</div>}
      <form className="category-create-form" onSubmit={createCategory}><label><span>Category name</span><input maxLength="200" placeholder="Coffee" required value={categoryName} onChange={(event)=>setCategoryName(event.target.value)}/></label><button className="primary-button" disabled={categoryBusy} type="submit">{categoryBusy?"Saving…":"Create category"}</button></form>
    </section> : null}

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
          const categoryProducts = products.filter((item)=>item.category===product.category); const productIndex = categoryProducts.findIndex((item)=>item.id===product.id);
          return <article className={`product-row ${state}${product.lunchSpecial ? " lunch-special-current" : ""}`} key={product.id}><div className="product-row-copy"><span className="product-row-thumb">{product.image ? <img alt="" loading="lazy" src={ownerProductImageUrl(product.image)} /> : <i aria-hidden="true">No image</i>}</span><strong>{product.name}</strong><span>{categoryName}{product.lunchSpecial ? " · Current Lunch Special" : ""}</span><p>{product.description || "No description"}</p></div><div className="product-row-meta"><strong>{money(product.price)}</strong><span className={`menu-state ${state}`}>{state === "unavailable" ? "Unavailable for ordering" : state === "available" ? "Available for ordering" : "Hidden from menu"}</span></div><div className="product-row-actions">{canManageAvailability ? <button className={product.available ? "sold-out-button" : "available-button"} disabled={availabilityBusy === product.id || !product.published} type="button" onClick={() => toggleAvailability(product)}>{availabilityBusy === product.id ? "Updating…" : product.available ? "Mark unavailable" : "Make available"}</button> : null}{canManageSpecial ? <button className={product.lunchSpecial ? "secondary-button" : "lunch-special-button"} disabled={lunchSpecialBusy || (!product.lunchSpecial && !canSelectSpecial)} title={!canSelectSpecial && !product.lunchSpecial ? "Only products visible on the customer menu can be selected." : undefined} type="button" onClick={() => changeLunchSpecial(product)}>{lunchSpecialBusy ? "Updating…" : product.lunchSpecial ? "Clear Lunch Special" : "Set as Lunch Special"}</button> : null}{canEdit ? <><button type="button" onClick={() => requestProductAction(() => startEdit(product))}>Edit</button><button aria-label={`Move ${product.name} up`} disabled={productIndex===0} type="button" onClick={()=>requestProductAction(()=>moveProduct(product,-1))}>Move up</button><button aria-label={`Move ${product.name} down`} disabled={productIndex===categoryProducts.length-1} type="button" onClick={()=>requestProductAction(()=>moveProduct(product,1))}>Move down</button></> : null}</div></article>;
        })}</div> : products.length === 0 && canEdit ? <div className="product-empty"><h3>{categories.length?`Now add your first product to ${categories[0].name}.`:"Create a category first."}</h3><p>{categories.length?"Add its name, price, and whether customers can order it.":"Products need a category so customers can browse your menu."}</p>{categories.length&&!creating?<button className="primary-button" type="button" onClick={()=>startCreate(categories[0].id)}>Add product</button>:null}</div> : <div className="product-empty"><Search size={28} /><h3>No matching products</h3><p>Try another search or clear the filters.</p><button className="secondary-button" type="button" onClick={() => { setQuery(""); setCategory("all"); setStatusFilter("all"); }}>Clear filters</button></div>}
      </section>

      {canEdit && categories.length && (creating || selectedProduct) ? <section className="product-editor-panel" aria-labelledby="product-editor-heading" ref={editorRef}><div className="section-heading"><div><p className="eyebrow">Product configuration</p><h2 id="product-editor-heading">{selectedProduct ? `Edit ${selectedProduct.name}` : "Add product"}</h2></div></div><form className="product-form" aria-busy={saving} onSubmit={handleSubmit}>
        <section className="product-editor-section" aria-labelledby="basic-information-heading"><div className="product-editor-section-heading"><h3 id="basic-information-heading">Basic information</h3><p>Describe the product and where customers can find it.</p></div>
          <label><span>Name</span><input ref={nameRef} required value={formProduct.name} onChange={(event) => updateField("name", event.target.value)} /></label>
          <label><span>Description</span><textarea rows="3" value={formProduct.description} onChange={(event) => updateField("description", event.target.value)} /></label>
          <div className="form-grid"><label><span>Base price (CAD)</span><span className="money-input"><b>$</b><input inputMode="decimal" min="0" required step="0.01" type="number" value={formProduct.price} onChange={(event) => updateField("price", event.target.value)} /></span><small>Used when this product has no variants.</small></label><label><span>Category</span><select required value={formProduct.category || categories[0]?.id || ""} onChange={(event) => updateField("category", event.target.value)}>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div>
          <section className="product-image-picker" aria-busy={uploading}>
            <div className="product-image-picker-intro"><strong>Product image (optional)</strong><p>Pick an illustrated JDS starter image to get going, or upload a photo of your actual product. You can change it anytime.</p><dl className="product-image-requirements"><div><dt>Recommended</dt><dd>Square image, 1:1</dd></div><div><dt>Minimum</dt><dd>{imageRequirements.product.minWidth} × {imageRequirements.product.minHeight} pixels</dd></div><div><dt>Formats</dt><dd>PNG, JPEG, WebP</dd></div><div><dt>Maximum</dt><dd>{maxUploadLabel}</dd></div></dl></div>
            <div className="product-image-current" aria-label="How customers will see this item">
              <div className="product-card-mini-preview">{formProduct.image?<img alt="Selected product image" src={ownerProductImageUrl(formProduct.image)}/>:<span className="product-card-mini-empty" aria-hidden="true">No image</span>}<div><b>{formProduct.name.trim()||"New item"}</b><small>{Number(formProduct.price)>=0&&formProduct.price!==""?money(Number(formProduct.price)):"Price"}</small></div></div>
              <div className="product-image-current-copy"><span className={`image-source-badge source-${productImageSource(formProduct.image)}`}>{productImageSourceLabel(formProduct.image)}</span>{formProduct.image.startsWith("starter:")?<><strong>JDS starter image selected</strong><small>Illustrated placeholder — replace it with your own photo anytime.</small></>:formProduct.image?<><strong>Selected for this product</strong><small>Customers see this image on your menu.</small></>:<small>Customers see a neutral placeholder until you add an image.</small>}</div>
            </div>
            {formProduct.image?<div className="product-image-source-actions"><button className="secondary-button" type="button" onClick={()=>{setImageLibraryOpen(false);setStarterPickerOpen((open)=>!open);}}>Choose another starter image</button><label className="secondary-button upload-button">{uploading?"Uploading…":"Replace with my own"}<input accept="image/png,image/jpeg,image/webp" disabled={uploading} type="file" onChange={uploadProductImage}/></label><button className="secondary-button" type="button" onClick={()=>{setStarterPickerOpen(false);setImageLibraryOpen((open)=>!open);}}>Choose from my images</button><button className="text-danger-button" type="button" disabled={uploading} onClick={removeProductImage}>Remove image</button></div>:<div className="product-image-source-actions"><button className="secondary-button" type="button" onClick={()=>{setImageLibraryOpen(false);setStarterPickerOpen((open)=>!open);}}>Choose a starter image</button><label className="secondary-button upload-button">{uploading?"Uploading…":"Upload my own"}<input accept="image/png,image/jpeg,image/webp" disabled={uploading} type="file" onChange={uploadProductImage}/></label><button className="secondary-button" type="button" onClick={()=>{setStarterPickerOpen(false);setImageLibraryOpen((open)=>!open);}}>Choose from my images</button></div>}
            {imageFeedback.message?<div className={`product-image-feedback ${imageFeedback.status}`} role={imageFeedback.status==="error"?"alert":"status"} aria-live="polite"><strong>{imageFeedback.fileName}</strong><span>{imageFeedback.message}</span>{imageFeedback.status==="error"?<small>Your current product image and draft were not changed.</small>:null}</div>:null}
            {starterPickerOpen?<section className="starter-image-picker" aria-label="JDS starter images"><div className="starter-picker-heading"><div><strong>JDS starter images</strong><small>Illustrated placeholders for cafés · {availableStarterMedia.length} to choose from · free, and they don’t use your photo allowance</small></div><button type="button" onClick={()=>setStarterPickerOpen(false)}>Close</button></div>
              {availableStarterMedia.length?<><div className="starter-picker-filters"><label><span>Search</span><input type="search" placeholder="Latte, muffin, soup…" value={starterQuery} onChange={(event)=>setStarterQuery(event.target.value)}/></label><label><span>Browse category</span><select value={starterCategory} onChange={(event)=>setStarterCategory(event.target.value)}><option value="all">All starter categories</option>{starterCategories.map((item)=><option key={item} value={item}>{starterCategoryLabel(item)}</option>)}</select></label></div>
              {starterSuggestions.length&&!starterQuery&&starterCategory==="all"?<div className="starter-suggestions"><strong>Suggested for “{formProduct.name}”</strong><StarterImageGrid assets={starterSuggestions.slice(0,4)} selected={formProduct.image} onSelect={chooseStarterImage}/></div>:null}
              {visibleStarterMedia.length?<StarterImageGrid assets={visibleStarterMedia} selected={formProduct.image} onSelect={chooseStarterImage}/>:<p className="starter-empty">No starter image matches that search. Try “coffee”, “muffin”, or “sandwich” — or upload your own photo.</p>}</>:<p className="starter-empty">Starter images aren’t available right now. Upload your own photo instead.</p>}
            </section>:null}
            {imageLibraryOpen?<section className="tenant-image-picker" aria-label="My images"><div className="starter-picker-heading"><div><strong>My images</strong><small>{demoLimits?`Free demo allowance: ${mediaUsage.files} of ${demoLimits.maxMediaFiles} photos · ${formatMegabytes(mediaUsage.bytes)} of ${formatMegabytes(demoLimits.maxStorageBytes)} used. Starter images don’t count.`:"Photos you have uploaded for this store."}</small></div><button type="button" onClick={()=>setImageLibraryOpen(false)}>Close</button></div>{media.length?<div className="media-library-grid">{media.map((asset)=>{const inUse=formProduct.image===asset.url||products.some((product)=>product.image===asset.url);return <div className="media-library-tile" key={asset.id}><button className={formProduct.image===asset.url?"is-selected":""} type="button" onClick={()=>{chooseProductImage(asset);setImageLibraryOpen(false);}}><img loading="lazy" src={asset.ownerUrl||asset.url} alt={asset.altText||"Uploaded image"}/><span>{asset.altText||"Uploaded image"}</span></button>{inUse?<small className="media-in-use">In use</small>:asset.purpose==="product"?<button className="media-remove-button" type="button" disabled={removingMediaId===asset.id} onClick={()=>removeUnusedImage(asset)}>{removingMediaId===asset.id?"Deleting…":"Delete unused photo"}</button>:null}</div>;})}</div>:<p>You have no suitable product images yet. Upload your own image to add one.</p>}</section>:null}
          </section>
        </section>
        <section className="product-editor-section product-variants" aria-labelledby="product-variants-heading"><div className="product-editor-section-heading"><h3 id="product-variants-heading">Variants (optional)</h3><p>Different versions or prices of the same item, such as Small, Medium, and Large.</p></div>
          {formProduct.variants.length ? <div className="product-variant-list">{formProduct.variants.map((variant, index) => <div className={variant.active === false ? "product-variant-row is-unavailable" : "product-variant-row"} key={variant.id || variant.key}>
            <label><span>Variant</span><input aria-label={`Variant ${index + 1} name`} placeholder="For example, 16oz Iced" required value={variant.name} onChange={(event) => updateVariant(index, "name", event.target.value)} /></label>
            <label><span>Price</span><input aria-label={`${variant.name || `Variant ${index + 1}`} price`} min="0" required step="0.01" type="number" value={variant.price} onChange={(event) => updateVariant(index, "price", event.target.value)} /></label>
            {variant.id ? <label className="variant-available-toggle"><input checked={variant.active !== false} type="checkbox" onChange={(event) => updateVariant(index, "active", event.target.checked)} /><span>Available</span></label> : <button aria-label={`Remove variant ${index + 1}`} className="variant-remove-button" type="button" onClick={() => removeNewVariant(index)}><Trash2 aria-hidden="true" size={17} /> Remove</button>}
          </div>)}</div> : <div className="variant-empty-state"><strong>No variants added.</strong><p>Customers will order this product at its base price.</p></div>}
          <button className="secondary-button add-variant-button" type="button" onClick={addVariant}><Plus aria-hidden="true" size={17} /> Add variant</button>
        </section>
        <section className="product-editor-section product-modifiers" aria-labelledby="product-modifiers-heading"><div className="product-editor-section-heading"><h3 id="product-modifiers-heading">Modifiers (optional)</h3><p>Customer choices or add-ons, such as Oat milk or an Extra shot.</p></div>{modifierGroups.some((group) => group.active) ? <div className="product-modifier-options">{modifierGroups.filter((group) => group.active || formProduct.modifierGroupIds.includes(group.id)).map((group) => { const assigned = formProduct.modifierGroupIds.includes(group.id); const preview = group.options.filter((item) => item.active).map((item) => `${item.name}${item.priceAdjustmentCents ? ` +$${(item.priceAdjustmentCents / 100).toFixed(2)}` : ""}`).join(" · "); return <label className={assigned ? "is-selected" : ""} key={group.id}><input checked={assigned} disabled={!group.active && !assigned} type="checkbox" onChange={() => toggleModifierGroup(group.id)} /><span><strong>{group.name}</strong><small>{preview || "No available modifiers yet"}{group.active ? "" : " · Category unavailable"}</small><b>{assigned ? "Available on this product" : "Not available on this product"}</b></span></label>; })}</div> : <div className="modifier-assignment-empty"><strong>No modifiers have been created yet.</strong></div>}<button className="secondary-button" type="button" onClick={() => setManagingModifiers(true)}>Manage modifiers</button></section>
        <section className="product-editor-section product-settings" aria-labelledby="product-settings-heading"><div className="product-editor-section-heading"><h3 id="product-settings-heading">Availability and placement</h3><p>Control where this product appears and whether it can be ordered.</p></div>
        <div className="product-state-controls" aria-label="Product visibility and placement">
          <label className={formProduct.available ? "product-state-toggle is-on" : "product-state-toggle"}><input checked={formProduct.available} type="checkbox" onChange={(event) => updateField("available", event.target.checked)} /><span aria-hidden="true" className="product-toggle-track" /><span><strong>Available for online ordering</strong><small>When visible, include it on the customer menu and allow ordering.</small></span></label>
          <label className={formProduct.published !== false ? "product-state-toggle is-on" : "product-state-toggle"}><input checked={formProduct.published !== false} type="checkbox" onChange={(event) => updateField("published", event.target.checked)} /><span aria-hidden="true" className="product-toggle-track" /><span><strong>Visible on customer menu</strong><small>Turn off to hide this product without archiving it.</small></span></label>
          <label className={formProduct.featured ? "product-state-toggle is-on" : "product-state-toggle"}><input checked={formProduct.featured} type="checkbox" onChange={(event) => updateField("featured", event.target.checked)} /><span aria-hidden="true" className="product-toggle-track" /><span><strong>Featured</strong><small>Highlight this product in customer recommendations.</small></span></label>
          <label className={formProduct.lunchSpecial ? "product-state-toggle is-on" : "product-state-toggle"}><input checked={formProduct.lunchSpecial} type="checkbox" onChange={(event) => updateField("lunchSpecial", event.target.checked)} /><span aria-hidden="true" className="product-toggle-track" /><span><strong>Lunch special</strong><small>Select as the current lunch special; choosing another product replaces it.</small></span></label>
        </div>
        </section>
        <div className="form-actions"><button className="primary-button" disabled={saving} type="submit">{saving ? "Saving…" : selectedProduct ? "Save changes" : "Add product"}</button><button className="secondary-button" type="button" onClick={() => requestProductAction(resetForm)}>Cancel</button>{selectedProduct?<button className="danger-button" type="button" onClick={()=>requestProductAction(async()=>{try{await removeProduct(selectedProduct.id);setNotice(`${selectedProduct.name} archived.`);resetForm();onCatalogChange?.();}catch(nextError){setNotice(nextError.message);}})}>Archive product</button>:null}</div>
      </form></section> : null}
    </div>
    <dialog aria-describedby="unsaved-product-message" aria-labelledby="unsaved-product-title" className="owner-confirm-dialog loyalty-unsaved-dialog" onCancel={stay} ref={dialogRef}><h2 id="unsaved-product-title">Unsaved product changes</h2><p id="unsaved-product-message">You have unsaved product changes. Leave without saving?</p><div className="form-actions"><button autoFocus className="secondary-button" type="button" onClick={stay}>Stay</button><button className="primary-button" type="button" onClick={leaveWithoutSaving}>Leave without saving</button></div></dialog>
  </section>;
}
