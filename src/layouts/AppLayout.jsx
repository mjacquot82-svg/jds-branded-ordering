import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Home, Search, ShoppingBag, UserRound } from "lucide-react";
import { useCustomerAuth } from "../auth/CustomerAuthContext.jsx";
import { useTenant } from "../tenant/TenantContext.jsx";

const customerLinks = [
  { to: "/", label: "Home", icon: Home, end: true },
  { to: "/menu", label: "Browse", icon: Search },
  { to: "/cart", label: "Cart", icon: ShoppingBag },
];

const operationalPathPrefixes = ["/admin", "/owner", "/staff", "/kitchen"];

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
  const primaryLinks = [
    ...customerLinks,
    {
      to: session ? "/account" : "/account/sign-in",
      label: "Account",
      icon: UserRound,
    },
  ];

  return (
    <div className="app-shell">
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
