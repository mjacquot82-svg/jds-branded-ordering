import PasswordResetPage from "../pages/PasswordResetPage.jsx";
import { OWNER_PASSWORD_MIN } from "../auth/passwordReset.js";
import { completeOwnerPasswordReset, requestOwnerPasswordReset } from "../services/ownerAuthApi.js";

export default function OwnerResetPasswordPage() {
  return <PasswordResetPage complete={completeOwnerPasswordReset} minLength={OWNER_PASSWORD_MIN} request={requestOwnerPasswordReset} signInPath="/owner/login" />;
}
