import { useEffect, useState } from "react";
import { BETA_NOTICE, PACKAGES, PACKAGE_NOTES, packagePrice } from "../services/packages.js";
import { fetchPackages } from "../services/designStudioApi.js";

/** Mobile-first package cards (stack on phones, 3 across on wide screens). Never charges anything. */
export default function PackagePicker({ value, onChange, disabled = false, heading = "Pick your package" }) {
  const [catalog, setCatalog] = useState({ packages: PACKAGES, notes: PACKAGE_NOTES, betaNotice: BETA_NOTICE });
  useEffect(() => { fetchPackages().then((data) => { if (Array.isArray(data?.packages) && data.packages.length) setCatalog(data); }).catch(() => {}); }, []);
  return (
    <section className="package-picker" aria-labelledby="package-picker-heading">
      <h2 id="package-picker-heading">{heading}</h2>
      <p className="package-beta-notice" role="note"><strong>{catalog.betaNotice}</strong></p>
      <div className="package-grid" role="radiogroup" aria-label="Packages">
        {catalog.packages.map((item) => {
          const selected = value === item.key;
          return (
            <button aria-checked={selected} className={`package-card${selected ? " is-selected" : ""}`} disabled={disabled} key={item.key} onClick={() => onChange(item.key)} role="radio" type="button">
              <span className="package-name">{item.name}</span>
              <span className="package-price">{packagePrice(item)} <small>CAD</small></span>
              {item.includes ? <span className="package-includes">{item.includes}</span> : null}
              <ul>{item.features.map((feature) => <li key={feature.label}>{feature.label}{feature.comingSoon ? <em className="package-soon"> Coming soon</em> : null}</li>)}</ul>
              <span className="package-select">{selected ? "✓ Selected" : `Choose ${item.name}`}</span>
            </button>
          );
        })}
      </div>
      <ul className="package-notes">{catalog.notes.map((note) => <li key={note}>{note}</li>)}</ul>
    </section>
  );
}
