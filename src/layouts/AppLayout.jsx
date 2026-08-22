import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Home, Search, ShoppingBag, UserRound } from "lucide-react";
import { useCustomerAuth } from "../auth/CustomerAuthContext.jsx";
import { useTenant } from "../tenant/TenantContext.jsx";
import { getLayoutDefinition } from "../design/layoutDefinitions.js";
import HeaderBrandingIdentity from "../design/HeaderBrandingIdentity.jsx";

function customerLinks(layout) { return [
  { to: "/", label: "Home", icon: Home, end: true },
  { to: "/menu", label: "Browse", icon: Search },
  { to: "/cart", label: "Cart", icon: ShoppingBag },
]; }

const operationalPathPrefixes = ["/admin", "/owner", "/staff", "/setup", "/activate", "/kitchen"];

export function isCustomerFacingPath(pathname) {
  return !operationalPathPrefixes.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
}

export default function AppLayout() {
  const { session } = useCustomerAuth();
  const tenant = useTenant();
  const { pathname } = useLocation();
  const showCustomerFooter = isCustomerFacingPath(pathname);
  const setupWizard = pathname === "/setup" || pathname.startsWith("/setup/") || pathname === "/activate";
  const storefrontLayout = getLayoutDefinition(tenant.value?.design?.template);
  const primaryLinks = [
    ...customerLinks(storefrontLayout),
    {
      to: session ? "/account" : "/account/sign-in",
      label: "Account",
      icon: UserRound,
    },
  ];

  if (setupWizard) return <div className="app-shell setup-app-shell"><main className="setup-shell-root"><Outlet /></main></div>;

  return (
    <div className={`app-shell storefront-layout-${storefrontLayout.id} navigation-${storefrontLayout.navigation}`}>
      {tenant.value?.review?.staging ? (
        <aside className="staging-review-banner" role="status">
          <strong>{tenant.value.review.label}</strong>
          <nav aria-label="Synthetic staging storefronts">
            <a href="/?review_tenant=the-guest-house">The Guest House TEST</a>
            <a href="/?review_tenant=second-street-cafe">Second Street Café TEST</a>
          </nav>
        </aside>
      ) : null}
      <header className="site-header">
        <div className="nav-container customer-nav-container">
          <NavLink className="storefront-header-brand" to="/"><HeaderBrandingIdentity config={tenant.value.design} layout={storefrontLayout} logoUrl={tenant.value.design.logoMediaId?`/api/v1/storefront/media/${tenant.value.design.logoMediaId}`:null}/></NavLink>
          <nav className="desktop-nav" aria-label="Desktop ordering navigation">
            {primaryLinks.map((link) => {
              const Icon = link.icon;
              return (
                <NavLink key={link.to} to={link.to} end={link.end}>
                  <Icon size={17} strokeWidth={2.35} />
                  <span>{link.label}</span>
                </NavLink>
              );
            })}
          </nav>
        </div>
      </header>
      {tenant.value?.design?.announcement?.enabled && tenant.value.design.announcement.text ? <aside className="storefront-announcement">{tenant.value.design.announcement.text}</aside> : null}

      <main>
        <Outlet />
      </main>

      {showCustomerFooter ? (
        <footer className="customer-footer">
          Jacquot Digital Solutions · Walkerton, Ont. ·{" "}
          <a href="https://jdsstudio.ca" rel="noopener noreferrer" target="_blank">
            jdsstudio.ca
          </a>
        </footer>
      ) : null}

      <nav className="bottom-nav" aria-label="Mobile ordering navigation">
        {primaryLinks.map((link) => {
          const Icon = link.icon;
          return (
            <NavLink key={link.to} to={link.to} end={link.end}>
              <Icon size={20} strokeWidth={2.35} />
              <span>{link.label}</span>
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}
