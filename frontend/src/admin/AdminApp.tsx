import '@tabler/core/dist/css/tabler.min.css';
import './admin.css';
import { Link, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import LoginPage from '../pages/LoginPage';
import CompanyProfilePage from '../pages/CompanyProfilePage';
import { runtimeConfig } from '../runtimeConfig';
import AdminDashboard from './AdminDashboard';
import AdminCosts from './AdminCosts';
import AuthBridgePage from '../auth/AuthBridgePage';
import { AdminCompaniesList, AdminCompanyDetail, AdminUsersList, AdminUserDetail } from './AdminDirectory';

function AdminGate() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="container-xl py-5">Loading administration…</div>;
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  if (user.role !== 'admin') return (
    <div className="container-xl py-5">
      <div className="alert alert-danger" role="alert">Administrator access is required.</div>
      <a href={runtimeConfig.appBaseUrl}>Return to GovVue Light</a>
    </div>
  );
  return <AdminLayout />;
}

function AdminLayout() {
  const { user, signOut } = useAuth();
  return (
    <div className="page admin-shell">
      <header className="navbar navbar-expand-md d-print-none">
        <div className="container-xl">
          <Link className="navbar-brand" to="/" aria-label="GovVue Light Admin home">
            <img className="admin-brand-mark" src="/govvue-light-logo.svg" alt="" aria-hidden="true" />
            <span>GovVue Light Admin</span>
          </Link>
          <nav className="admin-nav" aria-label="Administration">
            <Link to="/">Operations</Link>
            <Link to="/costs">Costs</Link>
            <Link to="/admin/users">Users</Link>
            <Link to="/admin/companies">Companies</Link>
            <a href={runtimeConfig.appBaseUrl}>Back to app ↗</a>
          </nav>
          <div className="admin-account"><span>{user?.email}</span><button className="btn btn-outline-secondary btn-sm" onClick={() => void signOut()}>Sign out</button></div>
        </div>
      </header>
      <main className="page-wrapper" id="main-content"><div className="container-xl py-4"><Outlet /></div></main>
    </div>
  );
}

export default function AdminApp() {
  return (
    <Routes>
      <Route path="/auth-bridge" element={<AuthBridgePage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route element={<AdminGate />}>
        <Route index element={<AdminDashboard />} />
        <Route path="/costs" element={<AdminCosts />} />
        <Route path="/admin/users" element={<AdminUsersList />} />
        <Route path="/admin/users/:username" element={<AdminUserDetail />} />
        <Route path="/admin/companies" element={<AdminCompaniesList />} />
        <Route path="/admin/companies/:companyId" element={<AdminCompanyDetail />} />
        <Route path="/admin/companies/:companyId/profile" element={<CompanyProfilePage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
