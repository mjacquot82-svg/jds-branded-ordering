export const NEUTRAL_RESET_MESSAGE = "If an account exists, we've sent a link. Check your email (and spam folder).";
export const OWNER_PASSWORD_MIN = 15;
export const CUSTOMER_PASSWORD_MIN = 10;

/** Supabase recovery links carry ?token_hash=… or #access_token=…&type=recovery. */
export function readRecoveryCredential(search = "", hash = "") {
  const query = new URLSearchParams(search);
  const fragment = new URLSearchParams(String(hash).replace(/^#/, ""));
  return {
    tokenHash: query.get("token_hash") || null,
    accessToken: fragment.get("access_token") || null,
    error: fragment.get("error_description") || query.get("error_description") || null,
  };
}

export function passwordProblem(password, confirm, minLength) {
  if (password.length < minLength) return `Use at least ${minLength} characters.`;
  if (password.length > 1024) return "Use 1024 characters or fewer.";
  if (password !== confirm) return "The two passwords don't match.";
  return "";
}
