import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { ownerEntryPath } from "../auth/ownerAuthRouting.js";
import {
  enterDemo,
  fetchDemoPilotConfig,
  fetchDemoPricing,
  resendDemoVerification,
  signupDemo,
} from "../services/demoFunnelApi.js";

function passwordHint(password, mode) {
  if (mode !== "signup") return null;
  if (!password) return "Use at least 10 characters. A passphrase works well.";
  if (password.length < 10) return `Need ${10 - password.length} more character${10 - password.length === 1 ? "" : "s"}.`;
  return "Password looks long enough.";
}

export default function BuildStoreLandingPage() {
  const { session, refreshSession } = useOwnerAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const onVerifyRoute = location.pathname.endsWith("/build/verify");
  const inviteFromLink = searchParams.get("invite") || "";

  const [pricing, setPricing] = useState(null);
  const [pilot, setPilot] = useState({ inviteRequired: false, captcha: { enabled: false } });
  const [mode, setMode] = useState(onVerifyRoute ? "enter" : "signup");
  const [form, setForm] = useState({
    email: searchParams.get("email") || "",
    password: "",
    business_name: "",
    contact_name: "",
    invite_code: inviteFromLink,
  });
  const [status, setStatus] = useState(
    onVerifyRoute
      ? {
          kind: "verify",
          message:
            "If you just opened your verification link, your email should now be confirmed. Sign in below with the same email and password to open your demo.",
        }
      : { kind: "idle" },
  );

  useEffect(() => {
    fetchDemoPricing()
      .then(setPricing)
      .catch(() =>
        setPricing({
          amountDisplay: "CAD $150.00/month",
          jdsSalesTakePercent: 0,
          disclosure: "JDS takes 0% of your sales. Processor fees still apply.",
        }),
      );
    fetchDemoPilotConfig()
      .then(setPilot)
      .catch(() => setPilot({ inviteRequired: false, captcha: { enabled: false } }));
  }, []);

  const hint = useMemo(() => passwordHint(form.password, mode), [form.password, mode]);

  if (session && ["owner", "manager"].includes(session.role)) {
    return <Navigate replace to={ownerEntryPath(session, "/admin/design")} />;
  }

  function update(field) {
    return (event) => setForm((current) => ({ ...current, [field]: event.target.value }));
  }

  async function submit(event) {
    event.preventDefault();
    setStatus({ kind: "working" });
    try {
      const result =
        mode === "signup"
          ? await signupDemo({
              email: form.email,
              password: form.password,
              business_name: form.business_name,
              contact_name: form.contact_name,
              invite_code: form.invite_code || undefined,
            })
          : await enterDemo({ email: form.email, password: form.password });
      if (result.status === "verification_required") {
        setStatus({
          kind: "verify",
          message: result.message,
          nextSteps: result.nextSteps || [],
          email: result.email || form.email,
        });
        setMode("enter");
        return;
      }
      await refreshSession?.();
      navigate("/admin/design", { replace: true });
    } catch (error) {
      const message =
        error.code === "invite_required"
          ? error.message || "A valid invite code is required for this pilot."
          : error.code === "account_exists"
            ? "An account already exists for this email. Switch to “I already started”."
            : error.code === "authentication_failed"
              ? "Email or password is incorrect. Try again, or reset via owner sign-in if this is a live merchant account."
              : error.message || "Unable to continue.";
      setStatus({ kind: "error", message, code: error.code });
    }
  }

  async function resend() {
    const email = status.email || form.email;
    if (!email) {
      setStatus({ kind: "error", message: "Enter your email first, then resend verification." });
      return;
    }
    setStatus((current) => ({ ...current, kind: "working" }));
    try {
      const result = await resendDemoVerification({ email });
      setStatus({
        kind: "verify",
        email,
        message: result.message,
        nextSteps: [
          "Check inbox and spam for the new link",
          "Open the link",
          "Then use “I already started” with the same password",
        ],
      });
      setMode("enter");
    } catch (error) {
      setStatus({ kind: "error", message: error.message || "Could not resend verification right now." });
    }
  }

  const amount = pricing?.amountDisplay || "CAD $150/month";

  return (
    <main className="page-section build-store-landing">
      <header className="build-store-hero">
        <p className="eyebrow">JDS Branded Ordering</p>
        <h1>Build Your Store Free</h1>
        <p>
          Create your branded café storefront — logo, colours, fonts, and menu — then preview on your phone.
          Save and return anytime. No credit card to build.
        </p>
        <ul className="build-store-points">
          <li>Start from the polished fictional Harbor &amp; Hearth café template (not a live shop)</li>
          <li>Customize branding and a starter menu, then preview safely</li>
          <li>Go live later for about {amount} — JDS takes <strong>0% of sales</strong></li>
          <li>Real orders and payments stay locked until JDS activates your live plan</li>
        </ul>
        {pricing?.disclosure ? <p className="build-store-disclosure">{pricing.disclosure}</p> : null}
        <p className="build-store-disclosure">
          Controlled pilot: shared privately with a small group. Not a public launch and not free live ecommerce.
        </p>
      </header>

      <section className="operations-panel build-store-card">
        <div className="login-action-row">
          <button
            className={mode === "signup" ? "primary-button" : "secondary-button"}
            type="button"
            onClick={() => {
              setMode("signup");
              setStatus({ kind: "idle" });
            }}
          >
            Build your store free
          </button>
          <button
            className={mode === "enter" ? "primary-button" : "secondary-button"}
            type="button"
            onClick={() => {
              setMode("enter");
              setStatus({ kind: "idle" });
            }}
          >
            I already started
          </button>
        </div>
        <form className="owner-login-form" onSubmit={submit}>
          {mode === "signup" ? (
            <>
              <label>
                Business name
                <input
                  required
                  maxLength={200}
                  value={form.business_name}
                  onChange={update("business_name")}
                  placeholder="Your café name"
                />
              </label>
              <label>
                Your name
                <input maxLength={200} value={form.contact_name} onChange={update("contact_name")} placeholder="Optional" />
              </label>
              {pilot.inviteRequired ? (
                <label>
                  Invite code
                  <input
                    required
                    maxLength={128}
                    value={form.invite_code}
                    onChange={update("invite_code")}
                    placeholder="From your JDS invite link"
                    autoComplete="one-time-code"
                  />
                </label>
              ) : null}
            </>
          ) : null}
          <label>
            Email
            <input required type="email" autoComplete="email" value={form.email} onChange={update("email")} />
          </label>
          <label>
            Password
            <input
              required
              type="password"
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              minLength={mode === "signup" ? 10 : 8}
              value={form.password}
              onChange={update("password")}
            />
          </label>
          {hint ? <p className="build-store-disclosure">{hint}</p> : null}
          {status.kind === "error" ? (
            <p className="form-error" role="alert">
              {status.message}
            </p>
          ) : null}
          {status.kind === "verify" ? (
            <div className="owner-page-message" role="status">
              <p>{status.message}</p>
              {Array.isArray(status.nextSteps) && status.nextSteps.length ? (
                <ol className="build-store-points">
                  {status.nextSteps.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
              ) : null}
              <button className="secondary-button" type="button" onClick={resend} disabled={!form.email && !status.email}>
                Resend verification email
              </button>
            </div>
          ) : null}
          <button className="primary-button" disabled={status.kind === "working"} type="submit">
            {status.kind === "working"
              ? "Working…"
              : mode === "signup"
                ? "Build your store free"
                : "Open my demo"}
          </button>
        </form>
        <p className="build-store-disclosure">
          One email = one demo workspace. Returning? Use <strong>I already started</strong> — do not create a second
          account.
        </p>
        <p>
          <Link to="/owner/login">Owner sign in</Link> for live merchants.
        </p>
      </section>
    </main>
  );
}
