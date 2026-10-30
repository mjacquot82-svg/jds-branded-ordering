import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { NEUTRAL_RESET_MESSAGE, passwordProblem, readRecoveryCredential } from "../auth/passwordReset.js";

/** Shared "Forgot password?" + "Choose a new password" page (owner and customer). */
export default function PasswordResetPage({ complete, minLength, request, signInPath, signInLabel = "Back to sign in" }) {
  const location = useLocation();
  const recovery = readRecoveryCredential(location.search, location.hash || window.location.hash);
  const hasRecovery = Boolean(recovery.tokenHash || recovery.accessToken);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShow] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState(recovery.error ? "This reset link is invalid or has expired. Request a new one." : "");
  const [done, setDone] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function submit(event) {
    event.preventDefault();
    if (isSubmitting) return;
    setError(""); setStatus("");
    if (hasRecovery) {
      const problem = passwordProblem(password, confirm, minLength);
      if (problem) { setError(problem); return; }
    }
    setIsSubmitting(true);
    try {
      if (hasRecovery) {
        await complete({ accessToken: recovery.accessToken, password, tokenHash: recovery.tokenHash });
        // Drop the one-time credential from the address bar.
        window.history.replaceState(null, "", location.pathname);
        setDone(true);
        setStatus("Your password is updated. Sign in with your new password.");
      } else {
        await request(email.trim());
        setStatus(NEUTRAL_RESET_MESSAGE);
      }
    } catch (failure) {
      if (!hasRecovery && failure?.status !== 429 && failure?.status) setStatus(NEUTRAL_RESET_MESSAGE);
      else if (failure?.status === 429) setError("Too many tries. Please wait a while and try again.");
      else if (hasRecovery) setError("This reset link is invalid or has expired. Request a new one below.");
      else setError("We couldn't reach the server. Please try again.");
    } finally { setIsSubmitting(false); }
  }

  return (
    <section className="page-section compact-section">
      <div className="operations-panel owner-login-panel">
        <h1>{hasRecovery ? "Choose a new password" : "Forgot password?"}</h1>
        {!hasRecovery ? <p>Enter the email you sign in with and we'll email you a link to set a new password.</p> : null}
        {!done ? <form className="owner-login-form" aria-isSubmitting={isSubmitting} onSubmit={submit}>
          {hasRecovery ? <>
            <p className="password-rules">Password rules: Use at least {minLength} characters (up to 1024). Spaces are allowed, so a short phrase works well. Don't reuse a password from another site.</p>
            <label>New password
              <span className="password-input-control">
                <input autoComplete="new-password" disabled={isSubmitting} maxLength={1024} minLength={minLength} required type={showPassword ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} />
                <button aria-label={showPassword ? "Hide password" : "Show password"} className="password-visibility-toggle" onClick={() => setShowPassword((v) => !v)} type="button">{showPassword ? <EyeOff aria-hidden="true" size={18} /> : <Eye aria-hidden="true" size={18} />}</button>
              </span>
            </label>
            <label>Confirm new password
              <input autoComplete="new-password" disabled={isSubmitting} maxLength={1024} required type={showPassword ? "text" : "password"} value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            </label>
          </> : <label>Email
            <input autoComplete="email" disabled={isSubmitting} required type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>}
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <button className="primary-button" disabled={isSubmitting} type="submit">{isSubmitting ? (hasRecovery ? "Updating…" : "Sending…") : (hasRecovery ? "Update password" : "Send reset link")}</button>
        </form> : null}
        {status ? <p className="form-status" aria-live="polite">{status}</p> : null}
        {hasRecovery && error ? <p><Link to={location.pathname}>Request a new link</Link></p> : null}
        <Link to={signInPath}>{signInLabel}</Link>
      </div>
    </section>
  );
}
