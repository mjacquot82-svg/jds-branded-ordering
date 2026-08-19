import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  getCategoryById,
  getCartLineId,
  getConfiguredPrice,
  getDefaultSelections,
  getMissingRequiredChoice,
  getModifierGroupsForProduct,
  getProductChoicePresentation,
  getProductSpecificImageUrl,
  getSelectedOptions,
  groupProductsByCategory,
  resolveMenuCategory,
} from "../services/menuCatalog.js";
import { useCustomerCatalog } from "../stores/customerCatalogStore.js";

function formatPrice(price) {
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
  }).format(price);
}

function getStoredCart() {
  try {
    return JSON.parse(window.localStorage.getItem("cafe-cart")) || [];
  } catch {
    return [];
  }
}

function storeCart(cart) {
  window.localStorage.setItem("cafe-cart", JSON.stringify(cart));
}

function ProductModifiers({ product, selections, onChange }) {
  const modifierGroups = getModifierGroupsForProduct(product);

  if (!modifierGroups.length) {
    return null;
  }

  return (
    <div className="modifier-stack">
      {modifierGroups.map((group) => (
        <fieldset key={group.id} className="modifier-group">
          <legend>{group.name}{group.required ? " (required)" : ""}</legend>
          <div className="modifier-options">
            {group.id !== "size" && !group.required ? <label className={selections[group.id] === "__none__" ? "selected" : ""}>
              <input checked={selections[group.id] === "__none__"} name={`${product.id}-${group.id}`} type="radio" onChange={() => onChange(group.id, "__none__")} />
              <span>No {group.name.toLowerCase()}</span>
            </label> : null}
            {group.options.map((option) => {
              const selectedValue = selections[group.id];
              const optionQuantity = group.allowQuantity ? Number(selectedValue?.[option.id] || 0) : 0;
              const hasDifferentOption = group.allowQuantity && group.type === "single" && Object.entries(selectedValue && selectedValue !== "__none__" ? selectedValue : {}).some(([id, quantity]) => id !== option.id && quantity > 0);
              const isSelected = group.allowQuantity ? optionQuantity > 0 : Array.isArray(selectedValue)
                ? selectedValue.includes(option.id)
                : selectedValue === option.id;

              return group.allowQuantity ? (
                <div key={option.id} className={`modifier-quantity-row${isSelected ? " selected" : ""}`}>
                  <span>{option.name}</span>
                  <div className="modifier-stepper" aria-label={`${option.name} quantity`}>
                    <button type="button" aria-label={`Remove one ${option.name}`} disabled={!optionQuantity} onClick={() => onChange(group.id, { ...(selectedValue && selectedValue !== "__none__" ? selectedValue : {}), [option.id]: Math.max(0, optionQuantity - 1) })}>−</button>
                    <output aria-live="polite">{optionQuantity}</output>
                    <button type="button" aria-label={`Add one ${option.name}`} disabled={hasDifferentOption || (group.maxSelections > 0 && Object.values(selectedValue && selectedValue !== "__none__" ? selectedValue : {}).reduce((sum, value) => sum + value, 0) >= group.maxSelections)} onClick={() => onChange(group.id, { ...(selectedValue && selectedValue !== "__none__" ? selectedValue : {}), [option.id]: optionQuantity + 1 })}>+</button>
                  </div>
                  {option.priceDelta ? <small>+{formatPrice(option.priceDelta)} each</small> : null}
                </div>
              ) : (
                <label key={option.id} className={isSelected ? "selected" : ""}>
                  <input
                    checked={isSelected}
                    name={`${product.id}-${group.id}`}
                    type={group.type === "multiple" ? "checkbox" : "radio"}
                    value={option.id}
                    onChange={(event) => {
                      if (group.type === "multiple") {
                        const current = Array.isArray(selectedValue) ? selectedValue : [];
                        onChange(
                          group.id,
                          event.target.checked
                            ? [...current, option.id]
                            : current.filter((item) => item !== option.id)
                        );
                        return;
                      }

                      onChange(group.id, option.id);
                    }}
                  />
                  <span>{option.name}</span>
                  {option.priceDelta ? <small>+{formatPrice(option.priceDelta)}</small> : null}
                </label>
              );
            })}
          </div>
        </fieldset>
      ))}
    </div>
  );
}

function ProductAddAction({ isAdded, missingChoice, quantity, onAdd }) {
  return (
    <div className="product-add-action">
      {quantity ? <span className="product-cart-quantity">{quantity} in cart</span> : null}
      <button
        className={`product-add-button${isAdded ? " is-added" : ""}`}
        disabled={Boolean(missingChoice)}
        type="button"
        onClick={onAdd}
      >
        <span>{missingChoice ? `Choose ${missingChoice.name}` : isAdded ? "Added — Add another" : quantity ? "Add another" : "Add to order"}</span>
      </button>
      {missingChoice ? <small className="product-choice-guidance">Choose {missingChoice.name.toLowerCase()}{missingChoice.id === "size" ? "" : ` or select No ${missingChoice.name.toLowerCase()}`}</small> : null}
    </div>
  );
}

export default function MenuPage() {
  const { status, catalog, reload } = useCustomerCatalog();
  const categories = catalog?.categories || [];
  const products = catalog?.products || [];
  const [searchParams, setSearchParams] = useSearchParams();
  const sections = useMemo(
    () => groupProductsByCategory(categories, products),
    [categories, products]
  );
  const categorySlug = searchParams.get("category") || "";
  const targetProductId = searchParams.get("product") || "";
  const targetProduct = products.find(
    (product) => product.id === targetProductId && product.available
  );
  const activeSectionId = resolveMenuCategory(sections, categorySlug, targetProduct);
  const [cart, setCart] = useState(getStoredCart);
  const [lastAdded, setLastAdded] = useState("");
  const [addedLineId, setAddedLineId] = useState("");
  const [bagIsUpdating, setBagIsUpdating] = useState(false);
  const [spotlightProductId, setSpotlightProductId] = useState("");
  const [expandedProductId, setExpandedProductId] = useState("");
  const [selectionsByProduct, setSelectionsByProduct] = useState({});
  const addedResetTimer = useRef(null);
  const bagPulseTimer = useRef(null);
  const spotlightTimer = useRef(null);

  useEffect(() => {
    return () => {
      clearTimeout(addedResetTimer.current);
      clearTimeout(bagPulseTimer.current);
      clearTimeout(spotlightTimer.current);
    };
  }, []);

  useEffect(() => {
    if (!targetProduct) {
      return;
    }

    setExpandedProductId(targetProduct.id);
  }, [targetProduct]);

  useEffect(() => {
    if (!targetProduct || activeSectionId !== targetProduct.category) {
      return;
    }

    clearTimeout(spotlightTimer.current);

    requestAnimationFrame(() => {
      const productCard = document.getElementById(`product-${targetProduct.id}`);

      if (!productCard) {
        return;
      }

      productCard.scrollIntoView({ behavior: "smooth", block: "center" });
      productCard.focus({ preventScroll: true });
      setSpotlightProductId(targetProduct.id);

      spotlightTimer.current = setTimeout(() => {
        setSpotlightProductId("");
      }, 1800);
    });
  }, [activeSectionId, targetProduct]);

  useEffect(() => {
    if (status !== "ready" || targetProduct || !categorySlug) {
      return;
    }
    if (categorySlug !== activeSectionId) {
      setSearchParams(activeSectionId ? { category: activeSectionId } : {}, { replace: true });
    }
  }, [activeSectionId, categorySlug, setSearchParams, status, targetProduct]);

  const activeMenuSection = sections.find((section) => section.id === activeSectionId);
  const availableItems = products.filter((product) => product.available);
  const featuredItems = availableItems.filter((product) => product.featured);

  const cartCount = useMemo(
    () => cart.reduce((total, item) => total + item.quantity, 0),
    [cart]
  );

  const cartTotal = useMemo(
    () => cart.reduce((total, item) => total + item.price * item.quantity, 0),
    [cart]
  );

  function getSelections(product) {
    return selectionsByProduct[product.id] || getDefaultSelections(product);
  }

  function updateSelection(productId, groupId, value) {
    setSelectionsByProduct((current) => ({
      ...current,
      [productId]: {
        ...current[productId],
        [groupId]: value,
      },
    }));
  }

  function addItem(product) {
    const selections = getSelections(product);
    const selectedOptions = getSelectedOptions(product, selections);
    const configuredPrice = getConfiguredPrice(product, selections);
    const cartLineId = getCartLineId(product, selectedOptions);
    const category = getCategoryById(categories, product.category);
    const cartItem = {
      id: cartLineId,
      productId: product.id,
      name: product.name,
      description: product.description,
      price: configuredPrice,
      basePrice: product.price,
      category: category?.name || product.category,
      options: selectedOptions.map((option) => ({
        groupName: option.groupName,
        name: option.name,
        priceDelta: option.priceDelta,
        quantity: option.quantity || 1,
        backendId: option.backendId,
        variantId: option.variantId,
        groupId: option.groupId,
      })),
    };
    const nextCart = cart.some((item) => item.id === cartLineId)
      ? cart.map((item) =>
          item.id === cartLineId ? { ...item, quantity: item.quantity + 1 } : item
        )
      : [...cart, { ...cartItem, quantity: 1 }];

    setCart(nextCart);
    storeCart(nextCart);
    setLastAdded(product.name);
    setAddedLineId(cartLineId);
    setBagIsUpdating(false);

    clearTimeout(addedResetTimer.current);
    clearTimeout(bagPulseTimer.current);

    requestAnimationFrame(() => {
      setBagIsUpdating(true);
    });

    addedResetTimer.current = setTimeout(() => {
      setAddedLineId("");
    }, 1700);

    bagPulseTimer.current = setTimeout(() => {
      setBagIsUpdating(false);
    }, 900);
  }

  function getItemQuantity(product) {
    const selections = getSelections(product);
    const cartLineId = getCartLineId(product, getSelectedOptions(product, selections));
    return cart.find((item) => item.id === cartLineId)?.quantity || 0;
  }

  if (status === "idle" || status === "loading") {
    return (
      <section className="page-section menu-page app-menu-page">
        <div className="app-menu-surface">
          <section className="menu-card menu-card-featured app-menu-card">
            <div className="empty-menu-note" role="status" aria-live="polite">
              <h1>Preparing the café menu</h1>
              <p>Gathering today’s drinks and fresh bites.</p>
            </div>
          </section>
        </div>
      </section>
    );
  }

  if (status === "error") {
    return (
      <section className="page-section menu-page app-menu-page">
        <div className="app-menu-surface">
          <section className="menu-card menu-card-featured app-menu-card">
            <div className="empty-menu-note" role="alert">
              <h1>We couldn’t load the café menu</h1>
              <p>Please check your connection and try again.</p>
              <button type="button" onClick={reload}>
                Try again
              </button>
            </div>
          </section>
        </div>
      </section>
    );
  }

  if (status === "empty") {
    return (
      <section className="page-section menu-page app-menu-page">
        <div className="app-menu-surface">
          <section className="menu-card menu-card-featured app-menu-card">
            <div className="empty-menu-note">
              <h1>No available items</h1>
              <p>The café menu is being updated. Please check back soon.</p>
            </div>
          </section>
        </div>
      </section>
    );
  }

  return (
    <section className="page-section menu-page app-menu-page">
      <div className="ordering-top-card">
        <div>
          <p className="eyebrow">Browse menu</p>
          <h1>Crafted drinks and fresh bites</h1>
          <p>Choose espresso, tea, breakfast, pastries, and seasonal café picks.</p>
        </div>
        <div className="order-meta-pills" aria-label="Menu summary">
          <span>{availableItems.length} items</span>
          <span>{featuredItems.length} favorites</span>
        </div>
      </div>

      <div
        className={`menu-order-strip app-order-strip${bagIsUpdating ? " is-updating" : ""}`}
        aria-live="polite"
      >
        <span>{lastAdded ? `${lastAdded} added` : "Build your café order"}</span>
        <strong key={`${cartCount}-${cartTotal}`}>
          {cartCount} {cartCount === 1 ? "item" : "items"} · {formatPrice(cartTotal)}
        </strong>
        <Link to="/cart">View cart</Link>
      </div>

      <div
        className={`cafe-bag-toast${bagIsUpdating ? " is-visible" : ""}`}
        role="status"
        aria-live="polite"
        aria-hidden={!bagIsUpdating}
      >
        Added to your café bag
      </div>

      <div className="menu-category-rail" aria-label="Menu categories">
        {sections.map((section) => (
          <button
            className={section.id === activeSectionId ? "active" : ""}
            type="button"
            key={section.id}
            onClick={() => {
              clearTimeout(spotlightTimer.current);
              setSpotlightProductId("");
              setExpandedProductId("");
              setSearchParams({ category: section.id });
            }}
          >
            {section.name}
          </button>
        ))}
      </div>

      <div className="app-menu-surface">
        <section className="menu-card menu-card-featured app-menu-card" aria-labelledby="active-menu-heading">
          {activeMenuSection ? (
            <>
              <div className="menu-card-heading">
                <div>
                  <h2 id="active-menu-heading">{activeMenuSection.name}</h2>
                  <p>{activeMenuSection.note}</p>
                </div>
              </div>

              <ul className="drink-card-grid">
                {activeMenuSection.items.map((item) => {
                  const selections = getSelections(item);
                  const missingChoice = getMissingRequiredChoice(item, selections);
                  const quantity = getItemQuantity(item);
                  const price = getConfiguredPrice(item, selections);
                  const category = getCategoryById(categories, item.category);
                  const cartLineId = getCartLineId(item, getSelectedOptions(item, selections));
                  const isAdded = addedLineId === cartLineId;
                  const choicePresentation = getProductChoicePresentation(item);

                  const isSpotlighted = spotlightProductId === item.id;
                  const isExpanded = expandedProductId === item.id;
                  const productImageUrl = getProductSpecificImageUrl(item);

                  return (
                    <li
                      className={`drink-card app-product-card${isSpotlighted ? " is-spotlighted" : ""}${isExpanded ? " is-expanded" : ""}${productImageUrl ? " has-product-image" : ""}`}
                      id={`product-${item.id}`}
                      key={item.id}
                      tabIndex={-1}
                    >
                      {productImageUrl ? <div className="product-thumb" style={{ backgroundImage: `url(${productImageUrl})` }} aria-hidden="true" /> : null}
                      <div className="product-card-main">
                        <div className="drink-card-title">
                          <div>
                            <span>{category?.name || "Cafe"}</span>
                            <h3>{item.name}</h3>
                          </div>
                          <strong>{formatPrice(price)}</strong>
                        </div>
                        <p>{item.description}</p>

                        {choicePresentation === "complex" ? (
                          <button className="product-customize-toggle" type="button" aria-expanded={isExpanded} aria-controls={`options-${item.id}`} onClick={() => setExpandedProductId(isExpanded ? "" : item.id)}>
                            {isExpanded ? "Collapse options" : "Customize"}
                          </button>
                        ) : null}

                        {choicePresentation === "direct" ? (
                          <ProductAddAction isAdded={isAdded} missingChoice={missingChoice} quantity={quantity} onAdd={() => addItem(item)} />
                        ) : (
                          <div
                            className={`product-customization${choicePresentation === "simple" ? " is-simple" : ""}`}
                            id={`options-${item.id}`}
                          >
                            <ProductModifiers
                              product={item}
                              selections={selections}
                              onChange={(groupId, value) => updateSelection(item.id, groupId, value)}
                            />

                            <ProductAddAction isAdded={isAdded} missingChoice={missingChoice} quantity={quantity} onAdd={() => addItem(item)} />
                          </div>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </>
          ) : (
            <div className="empty-menu-note">
              <h2>No available items</h2>
              <p>The cafe menu is being updated.</p>
            </div>
          )}
        </section>
      </div>
    </section>
  );
}
