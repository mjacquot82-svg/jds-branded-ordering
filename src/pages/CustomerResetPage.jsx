import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { completeCustomerPasswordReset, requestCustomerPasswordReset } from "../services/customerAuthApi.js";
import { getCustomerErrorMessage } from "../services/customerMessages.js";

export default function CustomerResetPage() {
  const [params] = useSearchParams();
  const recoveryParams = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const tokenHash = params.get("token_hash");
  const recoveryAccessToken = recoveryParams.get("access_token");
  const hasRecovery = Boolean(tokenHash || recoveryAccessToken);
  const [value, setValue] = useState("");
  const [status, setStatus] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  async function submit(event) {
    event.preventDefault();
    if (isSubmitting) return;
    setStatus("");
    setIsSubmitting(true);
    try {
      const result = hasRecovery
        ? await completeCustomerPasswordReset({ accessToken: recoveryAccessToken, password: value, tokenHash })
        : await requestCustomerPasswordReset(value);
      setStatus(result.message);
    } catch (error) {
      setStatus(getCustomerErrorMessage(error, hasRecovery ? "We couldn’t update your password. Please try again." : "We couldn’t send the reset link. Please try again."));
    } finally {
      setIsSubmitting(false);
    }
  }
  return <section className="page-section compact-section ordering-page"><div className="operations-panel"><h1>{hasRecovery ? "Choose a new password" : "Reset password"}</h1><form className="product-form" aria-busy={isSubmitting} onSubmit={submit}><label><span>{hasRecovery ? "New password" : "Email"}</span>{hasRecovery ? <span className="password-input-control"><input autoComplete="new-password" disabled={isSubmitting} required minLength={10} type={showPassword ? "text" : "password"} value={value} onChange={(event) => setValue(event.target.value)} /><button aria-label={showPassword ? "Hide password" : "Show password"} className="password-visibility-toggle" onClick={() => setShowPassword((visible) => !visible)} type="button">{showPassword ? <EyeOff aria-hidden="true" size={18} /> : <Eye aria-hidden="true" size={18} />}</button></span> : <input autoComplete="email" disabled={isSubmitting} required type="email" value={value} onChange={(event) => setValue(event.target.value)} />}{hasRecovery ? <small>Use at least 10 characters.</small> : null}</label><button className="primary-button" disabled={isSubmitting} type="submit">{isSubmitting ? (hasRecovery ? "Updating…" : "Sending…") : (hasRecovery ? "Update password" : "Send reset link")}</button>{status ? <p className="form-status" aria-live="polite">{status}</p> : null}</form><Link to="/login">Return to sign in</Link></div></section>;
}
