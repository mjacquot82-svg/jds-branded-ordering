import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./layouts/AppLayout.jsx";
import AdminDashboard from "./admin/AdminDashboard.jsx";
import OrdersPage from "./admin/OrdersPage.jsx";
import ProductsPage from "./admin/ProductsPage.jsx";
import SchedulingPage from "./admin/SchedulingPage.jsx";
import CartPage from "./pages/CartPage.jsx";
import ConfirmationPage from "./pages/ConfirmationPage.jsx";
import HomePage from "./pages/HomePage.jsx";
import MenuPage from "./pages/MenuPage.jsx";
import OrdersPageMobile from "./pages/OrdersPageMobile.jsx";
import AccountPage from "./pages/AccountPage.jsx";
import OwnerLoginPage from "./admin/OwnerLoginPage.jsx";
import RequireOwner from "./auth/RequireOwner.jsx";
import CustomerAuthPage from "./pages/CustomerAuthPage.jsx";
import CustomerVerifyPage from "./pages/CustomerVerifyPage.jsx";
import CustomerResetPage from "./pages/CustomerResetPage.jsx";
import OwnerAuthBoundary from "./auth/OwnerAuthBoundary.jsx";
import CommunicationsPage from "./admin/CommunicationsPage.jsx";
import StaffPage from "./admin/StaffPage.jsx";
import StaffLoginPage from "./admin/StaffLoginPage.jsx";
import LoyaltyPage from "./admin/LoyaltyPage.jsx";
import DesignStudioPage from "./admin/DesignStudioPage.jsx";
import OnboardingPage from "./admin/OnboardingPage.jsx";
import PlatformAdminPage from "./admin/PlatformAdminPage.jsx";
import DesignPreviewPage from "./admin/DesignPreviewPage.jsx";

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<HomePage />} />
        <Route path="menu" element={<MenuPage />} />
        <Route path="cart" element={<CartPage />} />
        <Route path="orders" element={<OrdersPageMobile />} />
        <Route path="account" element={<AccountPage />} />
        <Route path="login" element={<CustomerAuthPage mode="login" />} />
        <Route path="register" element={<CustomerAuthPage mode="register" />} />
        <Route path="account/sign-in" element={<CustomerAuthPage mode="login" />} />
        <Route path="account/create" element={<CustomerAuthPage mode="register" />} />
        <Route path="account/verify-email" element={<CustomerVerifyPage />} />
        <Route path="account/reset-password" element={<CustomerResetPage />} />
        <Route path="confirmation" element={<ConfirmationPage />} />
        <Route element={<OwnerAuthBoundary />}>
          <Route path="owner/login" element={<OwnerLoginPage />} />
          <Route path="staff" element={<StaffLoginPage />} />
          <Route path="admin" element={<RequireOwner />}>
            <Route index element={<AdminDashboard />} />
            <Route path="orders" element={<OrdersPage />} />
            <Route path="products" element={<ProductsPage />} />
            <Route path="scheduling" element={<SchedulingPage />} />
            <Route path="communications" element={<CommunicationsPage />} />
            <Route path="loyalty" element={<LoyaltyPage />} />
            <Route path="design" element={<DesignStudioPage />} />
            <Route path="design/preview" element={<DesignPreviewPage />} />
            <Route path="setup" element={<OnboardingPage />} />
            <Route path="platform" element={<PlatformAdminPage />} />
            <Route path="staff" element={<StaffPage />} />
            <Route path="*" element={<Navigate replace to="/admin" />} />
          </Route>
        </Route>
      </Route>
    </Routes>
  );
}
