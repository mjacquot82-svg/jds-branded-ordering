import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { resendCustomerVerification, verifyCustomerEmail } from "../services/customerAuthApi.js";
import { getCustomerErrorMessage } from "../services/customerMessages.js";
import { customerAuthHref, customerReturnFrom } from "../services/customerAuthReturn.js";

export default function CustomerVerifyPage() {
  const [params] = useSearchParams();
  const returnTo = customerReturnFrom(params);
  const [status, setStatus] = useState("Verifying your email…");
  const [email, setEmail] = useState("");
  const [canResend, setCanResend] = useState(false);
  const [isResending, setIsResending] = useState(false);
  useEffect(() => {
    const token = params.get("token_hash");
    if (!token) { setStatus("This verification link is incomplete."); setCanResend(true); return; }
    verifyCustomerEmail(token)
      .then((result) => setStatus(result.message))
      .catch((error) => { setStatus(getCustomerErrorMessage(error, "We couldn’t verify this email link.")); setCanResend(error.code === "verification_invalid"); });
  }, [params]);
  async function resendVerification(event) {
    event.preventDefault();
    if (isResending) return;
    setIsResending(true);
    try {
      const result = await resendCustomerVerification(email);
      setStatus(result.message);
    } catch (error) {
      setStatus(getCustomerErrorMessage(error, "We couldn’t resend the verification email. Please try again."));
    } finally {
      setIsResending(false);
    }
  }
  return <section className="page-section compact-section ordering-page"><div className="operations-panel"><h1>Email verification</h1><p role="status" aria-live="polite">{status}</p>{canResend ? <form className="product-form" aria-busy={isResending} onSubmit={resendVerification}><label><span>Email</span><input autoComplete="email" disabled={isResending} required type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label><button className="secondary-button" disabled={isResending} type="submit">{isResending ? "Sending…" : "Resend verification email"}</button></form> : null}<Link className="primary-button" to={customerAuthHref("/login", returnTo)}>Sign In</Link></div></section>;
}
