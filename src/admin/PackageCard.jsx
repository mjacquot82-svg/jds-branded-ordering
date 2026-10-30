import { useEffect, useState } from "react";
import PackagePicker from "../components/PackagePicker.jsx";
import { BETA_NOTICE, forgetPackage, packageName, rememberedPackage } from "../services/packages.js";
import { fetchOwnerPackage, saveOwnerPackage } from "../services/designStudioApi.js";

/** Owner dashboard: shows the chosen package and lets the owner change it. No billing. */
export default function PackageCard({ csrfToken, canChange }) {
  const [state, setState] = useState({ status: "loading" });
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    fetchOwnerPackage().then(async (value) => {
      const pending = rememberedPackage();
      if (!value.package && pending && canChange && csrfToken) {
        value = await saveOwnerPackage(pending, csrfToken).catch(() => value);
        forgetPackage();
      }
      setState({ status: "ready", ...value });
    }).catch(() => setState({ status: "error" }));
  }, [canChange, csrfToken]);
  async function choose(key) {
    setSaving(true);
    try { setState({ status: "ready", ...(await saveOwnerPackage(key, csrfToken)) }); setEditing(false); }
    catch { setState((current) => ({ ...current, saveError: "Couldn't save your package. Try again." })); }
    finally { setSaving(false); }
  }
  if (state.status === "loading") return null;
  return (
    <section className="operations-panel owner-package-card" aria-label="Your package">
      <h2>Your package: {state.status === "ready" && state.package ? packageName(state.package) : "Not chosen yet"}</h2>
      <p>{state.betaNotice || BETA_NOTICE}</p>
      {state.saveError ? <p className="form-error" role="alert">{state.saveError}</p> : null}
      {canChange ? <button className="secondary-button" type="button" onClick={() => setEditing(!editing)}>{editing ? "Close" : state.package ? "Change package" : "Choose a package"}</button> : null}
      {editing ? <PackagePicker value={state.package} onChange={choose} disabled={saving} heading="Choose your package" /> : null}
    </section>
  );
}
