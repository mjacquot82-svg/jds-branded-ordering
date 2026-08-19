import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { isOrderingCustomerSession, useCustomerAuth } from "../auth/CustomerAuthContext.jsx";
import { registerCustomer, resendCustomerVerification } from "../services/customerAuthApi.js";
import { getCustomerErrorMessage } from "../services/customerMessages.js";
import { formatCustomerPhone, isCompleteCustomerPhone, normalizeCustomerPhone } from "../services/customerPhone.js";
import { clearCustomerReturn, customerAuthHref, customerReturnFrom } from "../services/customerAuthReturn.js";
import { useTenant } from "../tenant/TenantContext.jsx";

export default function CustomerAuthPage({ mode }) {
  const { value: tenant } = useTenant();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const returnTo = customerReturnFrom(params);
  const { login } = useCustomerAuth();
  const [form, setForm] = useState({ name: "", email: "", password: "", phone: "" });
  const [keepSignedIn, setKeepSignedIn] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [status, setStatus] = useState("");
  const [verificationRequired, setVerificationRequired] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const creating = mode === "register";
  async function submit(event) {
    event.preventDefault();
    if (isSubmitting) return;
    setStatus(""); setVerificationRequired(false); setIsSubmitting(true);
    try {
      if (creating) {
        if (!isCompleteCustomerPhone(form.phone)) {
          setStatus("Enter a complete 10-digit phone number.");
          return;
        }
        const result = await registerCustomer(form.name, form.email, form.password, normalizeCustomerPhone(form.phone));
        setStatus(result.message);
      } else {
        const authenticatedSession = await login(form.email, form.password, keepSignedIn);
        if (returnTo === "/cart" && !isOrderingCustomerSession(authenticatedSession)) {
          setStatus("Ordering requires a customer account. Sign in with a customer account to continue.");
          return;
        }
        clearCustomerReturn();
        navigate(returnTo, { replace: true });
      }
    } catch (error) {
      if (!creating && error.code === "email_verification_required") {
        setVerificationRequired(true);
        setStatus("This email address has not been verified.");
      } else {
        setStatus(getCustomerErrorMessage(error, creating ? "We couldn’t create your account. Please try again." : "We couldn’t sign you in. Please try again."));
      }
    } finally {
      setIsSubmitting(false);
    }
  }
  async function resendVerification() {
    if (isResending) return;
    setStatus("");
    setIsResending(true);
    try {
      const result = await resendCustomerVerification(form.email);
      setStatus(result.message);
    } catch (error) {
      setStatus(getCustomerErrorMessage(error, "We couldn’t resend the verification email. Please try again."));
    } finally {
      setIsResending(false);
    }
  }
  return (
    <section className="page-section compact-section ordering-page">
      <div className="operations-panel">
        <p className="eyebrow">Customer account</p>
        <h1>{creating ? "Create Account" : "Sign In"}</h1>
        <p>{creating ? "Save your details for faster checkout and order history." : `Welcome back to ${tenant.business?.displayName || tenant.design?.displayName || "your café"}.`}</p>
        <form className="product-form" aria-busy={isSubmitting || isResending} onSubmit={submit}>
          {creating ? <label><span>Name</span><input autoComplete="name" disabled={isSubmitting} required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label> : null}
          <label><span>Email</span><input autoComplete="email" disabled={isSubmitting || isResending} required type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></label>
          {creating ? <label><span>Phone</span><input autoComplete="tel" disabled={isSubmitting} inputMode="numeric" pattern="\(\d{3}\) \d{3}-\d{4}" placeholder="(519) 881-6869" required type="tel" value={form.phone} onChange={(event) => setForm({ ...form, phone: formatCustomerPhone(event.target.value) })} /></label> : null}
          <label><span>Password</span><span className="password-input-control"><input autoComplete={creating ? "new-password" : "current-password"} disabled={isSubmitting} minLength={creating ? 10 : 8} required type={showPassword ? "text" : "password"} value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /><button aria-label={showPassword ? "Hide password" : "Show password"} className="password-visibility-toggle" onClick={() => setShowPassword((visible) => !visible)} type="button">{showPassword ? <EyeOff aria-hidden="true" size={18} /> : <Eye aria-hidden="true" size={18} />}</button></span>{creating ? <small>Use at least 10 characters.</small> : null}</label>
          {!creating ? <label className="auth-checkbox"><input checked={keepSignedIn} disabled={isSubmitting} type="checkbox" onChange={(event) => setKeepSignedIn(event.target.checked)} /><span>Keep me signed in</span></label> : null}
          <button className="primary-button" disabled={isSubmitting || isResending} type="submit">{isSubmitting ? (creating ? "Creating account…" : "Signing in…") : (creating ? "Create Account" : "Sign In")}</button>
          {status ? <p className="form-status" role={verificationRequired ? "alert" : "status"} aria-live="polite">{status}</p> : null}
          {verificationRequired ? <button className="secondary-button" disabled={isSubmitting || isResending} type="button" onClick={resendVerification}>{isResending ? "Sending…" : "Resend verification email"}</button> : null}
        </form>
        <div className="form-actions">
          <Link className="secondary-button" to={customerAuthHref(creating ? "/account/sign-in" : "/account/create", returnTo)}>{creating ? "Sign In" : "Create Account"}</Link>
          {!creating ? <Link to="/account/reset-password">Forgot password?</Link> : null}
        </div>
      </div>
    </section>
  );
}
