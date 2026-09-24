import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from './auth/AuthProvider';
import Layout from './components/Layout';
import LoginPage from './pages/LoginPage';
import OpportunityDetailPage from './pages/OpportunityDetailPage';
import SavedOpportunitiesPage from './pages/SavedOpportunitiesPage';
import SavedSearchesPage from './pages/SavedSearchesPage';
import SearchPage from './pages/SearchPage';
import DailyNotificationsPage from './pages/DailyNotificationsPage';
import DailyNotificationDetailPage from './pages/DailyNotificationDetailPage';
import DailyNotificationRunPage from './pages/DailyNotificationRunPage';
import AccountPage from './pages/AccountPage';
import AdminUsersPage from './pages/AdminUsersPage';
import EntitySearchPage from './pages/EntitySearchPage';
import SavedEntitiesPage from './pages/SavedEntitiesPage';
import SavedEntitySearchesPage from './pages/SavedEntitySearchesPage';
import EntityDetailPage from './pages/EntityDetailPage';
import PublicLayout from './components/PublicLayout';
import AboutPage from './pages/AboutPage';
import PrivacyPage from './pages/PrivacyPage';
import TermsPage from './pages/TermsPage';

function Protected() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <main className="grid-container padding-y-6"><p>Loading…</p></main>;
  return user ? <Outlet /> : <Navigate to="/login" replace state={{ from: location }} />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<PublicLayout />}>
        <Route path="/about" element={<AboutPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/terms" element={<TermsPage />} />
      </Route>
      <Route element={<Protected />}>
        <Route element={<Layout />}>
          <Route path="/search" element={<SearchPage />} />
          <Route path="/entities" element={<EntitySearchPage />} />
          <Route path="/entities/:uei" element={<EntityDetailPage />} />
          <Route path="/saved-entities" element={<SavedEntitiesPage />} />
          <Route path="/entity-searches" element={<SavedEntitySearchesPage />} />
          <Route path="/opportunities/:noticeId" element={<OpportunityDetailPage />} />
          <Route path="/saved" element={<SavedOpportunitiesPage />} />
          <Route path="/searches" element={<SavedSearchesPage />} />
          <Route path="/notifications" element={<DailyNotificationsPage />} />
          <Route path="/notifications/:notificationId" element={<DailyNotificationDetailPage />} />
          <Route path="/notifications/:notificationId/runs/:runDate" element={<DailyNotificationRunPage />} />
          <Route path="/account" element={<AccountPage />} />
          <Route path="/admin/users" element={<AdminUsersPage />} />
          <Route path="*" element={<Navigate to="/search" replace />} />
        </Route>
      </Route>
    </Routes>
  );
}
