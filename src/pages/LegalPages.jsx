import { useEffect } from "react";
import { Link } from "react-router-dom";
import { useTenant } from "../tenant/TenantContext.jsx";
import renderLegalMarkdown, { fillTemplate } from "../legal/renderLegalMarkdown.jsx";
import ownerTerms from "../legal/ownerTerms.md?raw";
import customerPrivacy from "../legal/customerPrivacy.md?raw";

const JDS_CONTACT = "contact@jdsstudio.ca";

function useTitle(title) {
  useEffect(() => { document.title = title; }, [title]);
}

export function customerPrivacyValues(tenant) {
  const business = tenant?.business || {};
  const name = business.displayName || tenant?.design?.displayName;
  const isShop = Boolean(tenant?.tenant?.slug && name);
  return {
    SHOP_NAME: isShop ? name : "the café you're ordering from",
    SHOP_CONTACT_EMAIL: (isShop && business.contactEmail) || JDS_CONTACT,
  };
}

export function TermsPage() {
  useTitle("Terms and Privacy · JDS");
  return (
    <article className="legal-page">
      {renderLegalMarkdown(ownerTerms)}
      <p><Link to="/privacy">Customer privacy notice</Link></p>
    </article>
  );
}

export function PrivacyPage() {
  const tenant = useTenant();
  const values = customerPrivacyValues(tenant.value);
  useTitle(`Privacy · ${values.SHOP_NAME}`);
  return (
    <article className="legal-page">
      {renderLegalMarkdown(fillTemplate(customerPrivacy, values))}
      <p><Link to="/terms">Terms for café owners</Link></p>
    </article>
  );
}

export function LegalLinks({ className = "legal-links" }) {
  return (
    <span className={className}>
      <Link to="/privacy">Privacy</Link> · <Link to="/terms">Terms</Link>
    </span>
  );
}
