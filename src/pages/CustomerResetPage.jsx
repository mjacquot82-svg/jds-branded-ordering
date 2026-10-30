import PasswordResetPage from "./PasswordResetPage.jsx";
import { CUSTOMER_PASSWORD_MIN } from "../auth/passwordReset.js";
import { completeCustomerPasswordReset, requestCustomerPasswordReset } from "../services/customerAuthApi.js";

export default function CustomerResetPage() {
  return <PasswordResetPage complete={completeCustomerPasswordReset} minLength={CUSTOMER_PASSWORD_MIN} request={requestCustomerPasswordReset} signInPath="/login" />;
}
