import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { dollarsToCents } from "../services/modifierMoney.js";
import { applySavedModifierGroup, isModifierDraftDirty } from "./modifierDraft.js";

let nextDraftId = 0;
const modifierDraft = (modifier = {}) => ({
  draftId: modifier.backendId || `new-modifier-${nextDraftId += 1}`,
  backendId: modifier.backendId,
  name: modifier.name || "",
  price: modifier.priceAdjustmentCents === undefined ? "0.00" : (modifier.priceAdjustmentCents / 100).toFixed(2),
  active: modifier.active !== false,
});

function categoryDraft(category, naturalOrder = 0) {
  if (category) return { ...category, choices: category.options.map(modifierDraft) };
  return {
    name: "", description: "", selectionType: "single", required: false,
    minSelections: 0, maxSelections: 1, active: true, allowQuantity: false, sortOrder: naturalOrder,
    choices: [],
  };
}

const priceLabel = (cents) => cents ? `+$${(cents / 100).toFixed(2)}` : "$0.00";

export default function ModifierManager({ groups, onClose, onSaveCustomization }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [draft, setDraft] = useState(null);
  const [savedDraft, setSavedDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [leaveOpen, setLeaveOpen] = useState(false);
  const dialogRef = useRef(null);
  const pendingLeaveRef = useRef(null);
  const allowNavigationRef = useRef(false);
  const busyRef = useRef(false);
  const editing = Boolean(draft?.backendId);
  const dirty = isModifierDraftDirty(draft, savedDraft);

  function loadCategory(category = null, addModifier = false) {
    const next = categoryDraft(category, groups.length);
    if (addModifier) next.choices = [...next.choices, modifierDraft()];
    setDraft(next);
    setSavedDraft(categoryDraft(category, groups.length));
    setMessage("");
  }

  const requestLeave = useCallback((action, navigation = false) => { pendingLeaveRef.current = { action, navigation }; setLeaveOpen(true); }, []);
  const requestDraftAction = useCallback((action) => { if (dirty) requestLeave(action); else action(); }, [dirty, requestLeave]);
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
  function closeDraft() { setDraft(null); setSavedDraft(null); setMessage(""); }

  function updateDraft(field, value) {
    setDraft((current) => {
      const next = { ...current, [field]: value };
      if (field === "selectionType" && value === "single") {
        next.minSelections = current.required ? 1 : 0;
      }
      if (field === "selectionType" && value === "multiple" && current.maxSelections === 1) next.maxSelections = 0;
      if (field === "required") next.minSelections = value ? 1 : 0;
      if (field === "allowQuantity" && value && current.maxSelections === 1) next.maxSelections = 0;
      return next;
    });
  }

  function updateModifier(draftId, field, value) {
    setDraft((current) => ({
      ...current,
      choices: current.choices.map((choice) => choice.draftId === draftId ? { ...choice, [field]: value } : choice),
    }));
  }

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    if (busyRef.current) return;
    if (!draft.name.trim()) return setMessage("Enter a name for this modifier category.");
    const choices = [];
    for (const choice of draft.choices) {
      if (!choice.name.trim()) return setMessage("Each modifier needs a name.");
      const cents = dollarsToCents(choice.price);
      if (cents === null) return setMessage(`Check the extra price for ${choice.name}. Use dollars and cents, such as 0.75.`);
      choices.push({ ...choice, priceAdjustmentCents: cents });
    }
    if ((draft.selectionType === "multiple" || draft.allowQuantity) && Number(draft.maxSelections) && Number(draft.maxSelections) < Number(draft.minSelections)) {
      return setMessage("Maximum total selections cannot be less than minimum selections.");
    }
    busyRef.current = true; setBusy(true); setMessage("");
    try {
      const result = await onSaveCustomization({ ...draft, name: draft.name.trim(), choices });
      const savedChoices = new Map(result.choices.map(({ clientId, response }) => [clientId, response]));
      const authoritativeDraft = applySavedModifierGroup(
        draft,
        result.group,
        choices.map((choice) => ({ ...choice, backendId: savedChoices.get(choice.draftId)?.id || choice.backendId })),
      );
      setDraft(authoritativeDraft);
      setSavedDraft(authoritativeDraft);
      setMessage(editing ? "Modifier category saved." : "Modifier category created. You can add modifiers now.");
    } catch (error) {
      const partial = error.partialCustomization;
      if (partial?.group) {
        const savedChoices = new Map(partial.choices.map(({ clientId, response }) => [clientId, response]));
        setDraft((current) => ({
          ...current, backendId: partial.group.id,
          choices: current.choices.map((choice) => ({ ...choice, backendId: savedChoices.get(choice.draftId)?.id || choice.backendId })),
        }));
      }
      setMessage(error.message || "This modifier category could not be saved. Your entries are still here; try again.");
    } finally { busyRef.current = false; setBusy(false); }
  }

  return <section className="modifier-manager" aria-labelledby="modifier-manager-heading">
    <header><div><p className="eyebrow">Product catalog</p><h1 id="modifier-manager-heading">Products</h1></div></header>
    <nav className="products-view-switch" aria-label="Products sections">
      <button type="button" onClick={() => requestDraftAction(onClose)}>Menu items</button>
      <button aria-current="page" className="is-active" type="button">Modifiers</button>
    </nav>
    {message ? <div className="product-notice" role="status" aria-live="polite">{message}</div> : null}

    {!draft ? <div className="modifier-catalog">
      <div className="modifier-catalog-heading"><div><p className="eyebrow">Modifiers</p><h2>Modifier catalog</h2></div>{groups.length ? <button className="primary-button" type="button" onClick={() => requestDraftAction(() => loadCategory())}>+ Add modifier category</button> : null}</div>
      {groups.length ? <div className="modifier-category-list">{groups.map((category) => <article className={`modifier-category${category.active ? "" : " is-unavailable"}`} key={category.backendId}>
        <header><div><h3>{category.name}</h3>{!category.active ? <span className="modifier-status">Unavailable</span> : null}</div><button className="secondary-button" type="button" onClick={() => requestDraftAction(() => loadCategory(category))}>Edit</button></header>
        {category.options.length ? <ul>{category.options.map((modifier) => <li className={modifier.active ? "" : "is-unavailable"} key={modifier.backendId}><span>{modifier.name}{!modifier.active ? <small>Unavailable</small> : null}</span><strong>{priceLabel(modifier.priceAdjustmentCents)}</strong></li>)}</ul> : <p className="modifier-category-empty">No modifiers in this category yet.</p>}
        <footer><small>Used on {category.assignmentCount} {category.assignmentCount === 1 ? "product" : "products"}</small><button type="button" onClick={() => requestDraftAction(() => loadCategory(category, true))}>+ Add modifier</button></footer>
      </article>)}</div> : <div className="modifier-empty"><h2>No modifiers yet.</h2><p>Create modifier categories for things customers can add or choose when ordering, such as milk choices or flavour shots.</p><button className="primary-button" type="button" onClick={() => requestDraftAction(() => loadCategory())}>Add modifier category</button></div>}
    </div> : <form className="modifier-editor" aria-busy={busy} onSubmit={submit}>
      <div className="modifier-editor-heading"><div><p className="eyebrow">{editing ? "Edit modifier category" : "Add modifier category"}</p><h2>{editing ? draft.name : "New modifier category"}</h2></div><button className="secondary-button" type="button" onClick={() => requestDraftAction(closeDraft)}>Back to modifiers</button></div>
      <label><span>Name</span><input autoFocus placeholder="For example, Milk" required value={draft.name} onChange={(event) => updateDraft("name", event.target.value)} /></label>
      {editing ? <label className="modifier-enabled"><input checked={draft.active} type="checkbox" onChange={(event) => updateDraft("active", event.target.checked)} /><span><strong>Available to customers</strong><small>Turn off safely while keeping product assignments and past order details.</small></span></label> : null}

      <details className="modifier-advanced"><summary>Advanced settings</summary><div className="modifier-advanced-fields">
        <fieldset><legend>How can customers choose?</legend><label className="modifier-setting-choice"><input checked={draft.selectionType === "single"} name="selection-type" type="radio" onChange={() => updateDraft("selectionType", "single")} /><span><strong>One option</strong><small>For example, choose one type of milk.</small></span></label><label className="modifier-setting-choice"><input checked={draft.selectionType === "multiple"} name="selection-type" type="radio" onChange={() => updateDraft("selectionType", "multiple")} /><span><strong>Multiple options</strong><small>For example, choose Vanilla and Caramel.</small></span></label></fieldset>
        <fieldset><legend>Can customers choose multiples of the same option?</legend><label className="modifier-enabled"><input checked={draft.allowQuantity} type="checkbox" onChange={(event) => updateDraft("allowQuantity", event.target.checked)} /><span><strong>Allow quantities</strong><small>For example, 2 sugars or 2 Vanilla shots.</small></span></label></fieldset>
        <fieldset><legend>Does the customer need to make a choice?</legend><label><input checked={!draft.required} name="requirement" type="radio" onChange={() => updateDraft("required", false)} /> No — they can choose None</label><label><input checked={draft.required} name="requirement" type="radio" onChange={() => updateDraft("required", true)} /> Yes — they must choose something</label></fieldset>
        {draft.selectionType === "multiple" || draft.allowQuantity ? <details className="modifier-selection-limits"><summary>Selection limits</summary><div className="modifier-limits">
          {draft.selectionType === "multiple" && draft.required ? <label><span>Minimum selections</span><input min="1" type="number" value={draft.minSelections} onChange={(event) => updateDraft("minSelections", Number(event.target.value))} /></label> : null}
          <label><span>{draft.allowQuantity ? "Maximum total selections" : "Maximum selections"} <small>(0 means no limit)</small></span><input min="0" type="number" value={draft.maxSelections} onChange={(event) => updateDraft("maxSelections", Number(event.target.value))} /></label>
        </div>{draft.allowQuantity ? <small>The maximum counts all units across this category.</small> : null}</details> : null}
      </div></details>

      {editing || draft.choices.length ? <section className="modifier-list-editor" aria-labelledby="modifier-list-editor-heading"><div><h3 id="modifier-list-editor-heading">Modifiers</h3><p>Add or edit the choices and extra prices customers see.</p></div>
        <div>{draft.choices.map((modifier) => <div className={`modifier-edit-row${modifier.active ? "" : " is-unavailable"}`} key={modifier.draftId}><label><span>Name</span><input placeholder="For example, Oat Milk" value={modifier.name} onChange={(event) => updateModifier(modifier.draftId, "name", event.target.value)} /></label><label><span>Extra price</span><span className="money-input"><b>$</b><input inputMode="decimal" min="0" placeholder="0.00" value={modifier.price} onChange={(event) => updateModifier(modifier.draftId, "price", event.target.value)} /></span></label><button className="secondary-button" type="button" onClick={() => modifier.backendId ? updateModifier(modifier.draftId, "active", !modifier.active) : setDraft((current) => ({ ...current, choices: current.choices.filter((item) => item.draftId !== modifier.draftId) }))}>{modifier.backendId ? modifier.active ? "Make unavailable" : "Make available" : "Remove"}</button>{!modifier.active ? <small>Unavailable to customers; retained for order history.</small> : null}</div>)}</div>
        <button className="secondary-button" type="button" onClick={() => setDraft((current) => ({ ...current, choices: [...current.choices, modifierDraft()] }))}>+ Add modifier</button>
      </section> : null}
      <div className="modifier-save-actions"><span aria-live="polite" className={`loyalty-save-status${dirty ? " is-unsaved" : ""}`}>{dirty ? "Unsaved changes" : ""}</span><button className="primary-button" disabled={busy || !dirty} type="submit">{busy ? "Saving…" : editing ? "Save changes" : "Save modifier category"}</button><button className="secondary-button" type="button" onClick={() => requestDraftAction(closeDraft)}>Cancel</button></div>
    </form>}
    <dialog aria-describedby="unsaved-modifier-message" aria-labelledby="unsaved-modifier-title" className="owner-confirm-dialog loyalty-unsaved-dialog" onCancel={stay} ref={dialogRef}><h2 id="unsaved-modifier-title">Unsaved modifier changes</h2><p id="unsaved-modifier-message">You have unsaved changes. Leave without saving?</p><div className="form-actions"><button autoFocus className="secondary-button" type="button" onClick={stay}>Stay</button><button className="primary-button" type="button" onClick={leaveWithoutSaving}>Leave without saving</button></div></dialog>
  </section>;
}
