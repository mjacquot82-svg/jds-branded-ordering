import { Link } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { ShoppingBag } from "lucide-react";
import {
  createQuickOrderItems,
  createHomeCatalogView,
  getHomeCategoryById,
} from "../services/homeCatalog.js";
import {
  getCartLineId,
  getConfiguredPrice,
  getDefaultSelections,
  getMissingRequiredChoice,
  getProductSpecificImageUrl,
  resolveQuickConfigurationSelections,
  getSelectedOptions,
} from "../services/menuCatalog.js";
import { useCustomerCatalog } from "../stores/customerCatalogStore.js";
import { useCustomerAuth } from "../auth/CustomerAuthContext.jsx";
import { fetchCustomerLoyalty } from "../services/loyaltyApi.js";
import { fetchCustomerQuickOrder } from "../services/customerAccountApi.js";
import { formatConfigurationDescription } from "../services/configurationDescription.js";
import LoyaltyCard from "../components/LoyaltyCard.jsx";
import { readTenantLocalStorage, writeTenantLocalStorage } from "../services/tenantBrowserState.js";
import { useTenant } from "../tenant/TenantContext.jsx";

function formatPrice(price) {
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(price);
}

function getStoredCart() {
  try {
    const stored = JSON.parse(readTenantLocalStorage("cafe-cart"));
    return Array.isArray(stored) ? stored : [];
  } catch {
    return [];
  }
}

function storeCart(cart) {
  writeTenantLocalStorage("cafe-cart", JSON.stringify(cart));
}

export default function HomePage() {
  const { value: tenant } = useTenant();
  const { session } = useCustomerAuth();
  const [quickOrderPersonalization, setQuickOrderPersonalization] = useState({
    productIds: [],
    configurations: [],
    userId: null,
  });
  const personalizedProductIds =
    quickOrderPersonalization.userId === session?.user_id
      ? quickOrderPersonalization.productIds
      : [];
  useEffect(() => {
    let active = true;
    setQuickOrderPersonalization({ productIds: [], userId: null });
    if (!session) return () => { active = false; };
    const userId = session.user_id;
    fetchCustomerQuickOrder()
      .then((value) => {
        if (active && Array.isArray(value.product_ids)) {
          setQuickOrderPersonalization({ productIds: value.product_ids, configurations: Array.isArray(value.configurations) ? value.configurations : [], userId });
        }
      })
      .catch(() => {
        if (active) setQuickOrderPersonalization({ productIds: [], userId: null });
      });
    return () => { active = false; };
  }, [session]);
  const [loyalty,setLoyalty]=useState({program:null,loading:false,error:""});
  useEffect(()=>{let active=true;if(!session){setLoyalty({program:null,loading:false,error:""});return()=>{active=false}}setLoyalty({program:null,loading:true,error:""});fetchCustomerLoyalty().then(value=>{if(active)setLoyalty({program:value.programs?.[0]||null,loading:false,error:""})}).catch(()=>{if(active)setLoyalty({program:null,loading:false,error:"unavailable"})});return()=>{active=false}},[session]);
  const { status, catalog, reload } = useCustomerCatalog();
  const {
    categories,
    popularItems,
    lunchSpecial,
  } = createHomeCatalogView(status, catalog);
  const availableProducts = (catalog?.products || []).filter(
    (product) => product.available
  );
  const quickCategories = categories
    .map((category) => {
      const categoryProducts = availableProducts.filter(
        (product) => product.category === category.id
      );

      return {
        ...category,
        count: categoryProducts.length,
        preview: categoryProducts
          .slice(0, 2)
          .map((product) => product.name)
          .join(" · "),
      };
    })
    .filter((category) => category.count)
    .slice(0, 6);
  const productsByBackendId = new Map((catalog?.products || []).map((product) => [product.backendId, product]));
  const exactQuickOrderItems = (quickOrderPersonalization.configurations || []).map((configuration) => {
    const product = productsByBackendId.get(configuration.product_id);
    const quickSelections = resolveQuickConfigurationSelections(product, configuration);
    return product && quickSelections ? { ...product, quickConfiguration: configuration, quickSelections, quickKey: `${configuration.product_id}:${configuration.variant_id || "standard"}:${configuration.modifiers.map((modifier) => `${modifier.option_id}x${modifier.quantity}`).join("|")}` } : null;
  }).filter(Boolean);
  const fallbackQuickOrderItems = createQuickOrderItems(catalog?.products || [], {
    personalizedProductIds: exactQuickOrderItems.length ? [] : personalizedProductIds,
    limit: Math.max(0, 6 - exactQuickOrderItems.length),
  }).filter((product) => !exactQuickOrderItems.some((exact) => exact.id === product.id)).map((product) => ({ ...product, quickConfiguration: null, quickKey: product.id }));
  const quickOrderItems = [...exactQuickOrderItems, ...fallbackQuickOrderItems].slice(0, 6);
  const hasPersonalizedQuickOrder = personalizedProductIds.some((productId) =>
    quickOrderItems.some((product) => product.backendId === String(productId))
  );
  const [cart, setCart] = useState(getStoredCart);
  const [lastAdded, setLastAdded] = useState("");
  const cartCount = useMemo(
    () => cart.reduce((total, item) => total + item.quantity, 0),
    [cart]
  );
  const cartTotal = useMemo(
    () => cart.reduce((total, item) => total + item.price * item.quantity, 0),
    [cart]
  );

  const recommendation = lunchSpecial || popularItems[0] || availableProducts[0] || null;
  const recommendationImageUrl = getProductSpecificImageUrl(recommendation);

  function addQuickItem(product) {
    const selections = product.quickSelections || getDefaultSelections(product);
    const selectedOptions = getSelectedOptions(product, selections);
    const configuredPrice = getConfiguredPrice(product, selections);
    const cartLineId = getCartLineId(product, selectedOptions);
    const category = getHomeCategoryById(categories, product.category);
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
      ? cart.map((item) => item.id === cartLineId
        ? { ...item, quantity: item.quantity + 1 }
        : item)
      : [...cart, { ...cartItem, quantity: 1 }];

    setCart(nextCart);
    storeCart(nextCart);
    setLastAdded(product.name);
  }

  return (
    <section className="home-page ordering-page">
      <div className="welcome-panel app-welcome-panel">
        {tenant.tenant.slug === "the-guest-house" ? <img className="ladels-hero-logo" src="/cafe.png" alt="Ladel's Wellness Café" /> : <div className="tenant-hero-wordmark"><strong>{tenant.design.displayName}</strong><span>{tenant.design.tagline}</span></div>}
      </div>

      <div className="home-order-status" aria-live="polite">
        <div>
          <ShoppingBag size={18} strokeWidth={2.4} />
          <span>{lastAdded ? `${lastAdded} added` : "Your café bag"}</span>
        </div>
        <Link to="/cart">
          {cartCount} {cartCount === 1 ? "item" : "items"} · {formatPrice(cartTotal)}
        </Link>
      </div>

      {status === "ready" || status === "empty" ? <section
        className={`content-block app-content-block lunch-special-block${recommendationImageUrl ? " has-product-image" : " is-image-free"}`}
        aria-labelledby="lunch-special-heading"
      >
        {recommendationImageUrl ? (
          <div
            className="lunch-special-image"
            style={{ backgroundImage: `url(${recommendationImageUrl})` }}
            aria-hidden="true"
          />
        ) : null}
        <div className="lunch-special-copy">
          <p className="eyebrow">{lunchSpecial ? "Today’s lunch special" : "From the café"}</p>
          <h2 id="lunch-special-heading" className="visually-hidden">{lunchSpecial ? "Today’s Lunch Special" : "Today’s Picks"}</h2>
          <h3>{recommendation?.name || "Something delicious is always waiting"}</h3>
          {recommendation?.description ? <p>{recommendation.description}</p> : null}
          {recommendation ? (
            <strong>{formatPrice(getConfiguredPrice(recommendation, getDefaultSelections(recommendation)))}</strong>
          ) : null}
          <Link
            className="primary-button"
            to={recommendation ? `/menu?product=${encodeURIComponent(recommendation.id)}` : "/menu"}
          >
            {lunchSpecial ? "Order Today’s Special" : "Browse today’s menu"}
          </Link>
        </div>
      </section> : null}

      {status === "idle" || status === "loading" ? (
        <section className="content-block app-content-block lunch-special-block is-image-free" aria-labelledby="lunch-special-loading-heading">
          <div className="lunch-special-copy" role="status" aria-live="polite">
            <p className="eyebrow">Today’s lunch special</p>
            <h2 id="lunch-special-loading-heading">Loading today’s special…</h2>
            <p>We’re checking the current café menu.</p>
          </div>
        </section>
      ) : null}

      {status === "error" ? (
        <section className="content-block app-content-block lunch-special-block is-image-free" aria-labelledby="lunch-special-error-heading">
          <div className="lunch-special-copy" role="alert">
            <p className="eyebrow">Today’s lunch special</p>
            <h2 id="lunch-special-error-heading">Today’s special is temporarily unavailable</h2>
            <p>We couldn’t load the current café menu. Please try again.</p>
            <button className="primary-button" type="button" onClick={reload}>Try again</button>
          </div>
        </section>
      ) : null}

      <section
        className="content-block app-content-block home-category-block"
        aria-labelledby="quick-order-heading"
      >
        <div className="section-heading">
          <h2 id="quick-order-heading">Browse the café</h2>
          <Link to="/menu">View full menu</Link>
        </div>

        {status === "ready" ? (
          <div className="category-pill-grid">
            {quickCategories.map((category) => (
              <Link className="category-pill-card" to={`/menu?category=${encodeURIComponent(category.slug)}`} key={category.id}>
                <span className="category-pill-copy">
                  <strong>{category.name}</strong>
                  <small>{category.preview}</small>
                </span>
                <span className="category-pill-count">
                  {category.count} {category.count === 1 ? "item" : "items"}
                </span>
              </Link>
            ))}
          </div>
        ) : null}

        {status === "idle" || status === "loading" ? (
          <div className="category-browser-state" role="status" aria-live="polite">
            <strong>Preparing the café menu</strong>
            <p>Coffee, tea, meals, and cold drinks will be ready in a moment.</p>
          </div>
        ) : null}

        {status === "error" ? (
          <div className="category-browser-state" role="alert">
            <strong>Browse the full café menu</strong>
            <p>Categories could not be loaded right now.</p>
            <div><Link to="/menu">Open menu</Link><button type="button" onClick={reload}>Try again</button></div>
          </div>
        ) : null}

        {status === "empty" ? (
          <div className="category-browser-state">
            <strong>Today’s menu is being prepared</strong>
            <p>Please check back soon for coffee, tea, meals, and more.</p>
          </div>
        ) : null}
      </section>

      {status === "ready" ? (
      <section className="content-block app-content-block quick-add-block" aria-labelledby="quick-order-heading-home">
        <div className="section-heading">
          <div>
            <h2 id="quick-order-heading-home">Quick Order</h2>
            {hasPersonalizedQuickOrder ? <p>Based on what you order most</p> : null}
          </div>
          <Link to="/menu">View menu</Link>
        </div>
        <div className="quick-product-rail">
          {quickOrderItems.map((item) => {
            const productImageUrl = getProductSpecificImageUrl(item);
            const QuickOrderCard = item.quickConfiguration ? "article" : Link;
            const quickOrderCardProps = item.quickConfiguration ? {} : {
              "aria-label": `Customize ${item.name}`,
              to: `/menu?product=${encodeURIComponent(item.id)}`,
            };

            return (
              <QuickOrderCard {...quickOrderCardProps} className={`quick-product-card${item.quickConfiguration ? " is-exact" : ""}${productImageUrl ? " has-product-image" : " is-image-free"}`} key={item.quickKey}>
                {productImageUrl ? (
                  <div className="quick-product-image" style={{ backgroundImage: `url(${productImageUrl})` }} aria-hidden="true" />
                ) : null}
                <div className="quick-product-copy">
                  {item.quickConfiguration ? <span className="quick-usual-label">Your usual</span> : null}
                  <h3>{item.name}</h3>
                  {item.quickConfiguration ? <small>{formatConfigurationDescription([
                    ...(() => {
                      const size = item.modifierGroups.find((group) => group.id === "size");
                      const option = size?.options.find((candidate) => candidate.backendId === item.quickConfiguration.variant_id);
                      return size && option ? [{ groupName: size.name, name: option.name }] : [];
                    })(),
                    ...item.modifierGroups.filter((group) => group.id !== "size").flatMap((group) => {
                      const selected = item.quickConfiguration.modifiers.filter((modifier) => group.options.some((option) => option.backendId === modifier.option_id));
                      return selected.map((modifier) => ({ groupName: group.name, name: modifier.option_name, quantity: modifier.quantity }));
                    }),
                  ]) || "Standard"}</small> : <small>Customize on the menu</small>}
                  <strong>{formatPrice(item.quickConfiguration ? getConfiguredPrice(item, item.quickSelections) : getConfiguredPrice(item, getDefaultSelections(item)))}</strong>
                </div>
                {item.quickConfiguration ? <button type="button" aria-label={`Order your usual ${item.name}`} title="Order this exact configuration" onClick={() => addQuickItem(item)}>
                  <span>Order</span>
                </button> : null}
              </QuickOrderCard>
            );
          })}
        </div>
      </section>
      ) : null}

      <LoyaltyCard error={loyalty.error} loading={loyalty.loading} program={loyalty.program} signedIn={Boolean(session)} />
    </section>
  );
}
