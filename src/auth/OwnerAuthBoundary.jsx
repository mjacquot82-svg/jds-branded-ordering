import { Outlet } from "react-router-dom";
import { OwnerAuthProvider } from "./OwnerAuthContext.jsx";

export default function OwnerAuthBoundary() {
  return (
    <OwnerAuthProvider>
      <Outlet />
    </OwnerAuthProvider>
  );
}
