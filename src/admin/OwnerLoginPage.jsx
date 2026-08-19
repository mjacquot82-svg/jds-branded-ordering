import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { useOwnerAuth } from "../auth/OwnerAuthContext.jsx";
import { safeAdminReturnTo } from "../auth/ownerAuthRouting.js";

export default function OwnerLoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { login, session } = useOwnerAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(searchParams.get("denied") ? "This account does not have owner portal access." : "");
  const [submitting, setSubmitting] = useState(false);
  const returnTo = safeAdminReturnTo(searchParams.get("returnTo"));

  if (session && ["owner", "manager"].includes(session.role)) return <Navigate replace to={returnTo} />;

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const nextSession = await login(email, password);
      if (!["owner", "manager"].includes(nextSession.role)) {
        setError("This account does not have owner portal access.");
        return;
      }
      navigate(returnTo, { replace: true });
    } catch (loginError) {
      setError(loginError.message || "Unable to sign in.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="page-section compact-section">
      <div className="operations-panel owner-login-panel">
        <h1>Owner sign in</h1>
        <p>Sign in with your verified JDS owner account.</p>
        <form className="owner-login-form" onSubmit={handleSubmit}>
          <label>
            Email
            <input autoComplete="email" name="email" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} />
          </label>
          <label>
            Password
            <input autoComplete="current-password" name="password" onChange={(event) => setPassword(event.target.value)} required type="password" value={password} />
          </label>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <div className="login-action-row">
            <button className="primary-button" disabled={submitting} type="submit">
              {submitting ? "Signing in…" : "Sign in"}
            </button>
            <Link className="secondary-button" to="/staff">Staff Access</Link>
          </div>
        </form>
      </div>
    </section>
  );
}
