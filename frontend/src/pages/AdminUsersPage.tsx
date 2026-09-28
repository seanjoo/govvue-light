import { FormEvent, useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthProvider';
import { api } from '../lib/api';
import type { AdminUser, Company } from '../types';

export default function AdminUsersPage() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<'user' | 'admin'>('user');
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [companyName, setCompanyName] = useState('');
  const [creatingCompany, setCreatingCompany] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  async function load() {
    setLoading(true);
    try {
      const [userResponse, companyResponse] = await Promise.all([
        api<{ items: AdminUser[] }>('/admin/users'),
        api<{ items: Company[] }>('/admin/companies'),
      ]);
      setUsers(userResponse.items);
      setCompanies(companyResponse.items);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load users');
    } finally {
      setLoading(false);
    }
  }

  async function createCompany(event: FormEvent) {
    event.preventDefault();
    setCreatingCompany(true);
    setError('');
    setMessage('');
    try {
      const created = await api<Company>('/admin/companies', {
        method: 'POST',
        body: JSON.stringify({ name: companyName }),
      });
      setCompanyName('');
      setMessage(`Created company workspace “${created.name}”.`);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to create company');
    } finally {
      setCreatingCompany(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function create(event: FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError('');
    setMessage('');
    try {
      const created = await api<AdminUser>('/admin/users', {
        method: 'POST',
        body: JSON.stringify({ email, role }),
      });
      setEmail('');
      setRole('user');
      const sesNote = created.ses_status === 'verified'
        ? 'The recipient is already verified in SES.'
        : 'SES recipient verification was requested for daily emails while the account is sandboxed.';
      setMessage(`Created ${created.email}. Cognito emailed a generated temporary password. ${sesNote}`);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to create user');
    } finally {
      setCreating(false);
    }
  }

  async function update(username: string, nextRole: 'user' | 'admin', enabled: boolean) {
    setError('');
    setMessage('');
    try {
      await api(`/admin/users/${encodeURIComponent(username)}`, {
        method: 'PUT',
        body: JSON.stringify({ role: nextRole, enabled }),
      });
      setMessage('User updated. Role changes appear after the user refreshes their session or signs in again.');
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to update user');
    }
  }

  async function updateAccess(username: string, companyId: string, companyRole: 'manager' | 'member', features: string[]) {
    setError('');
    setMessage('');
    try {
      await api(`/admin/users/${encodeURIComponent(username)}/access`, {
        method: 'PUT',
        body: JSON.stringify({ company_id: companyId, company_role: companyRole, features }),
      });
      setMessage('Company access and feature toggles updated.');
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to update company access');
    }
  }

  async function sendReset(target: AdminUser) {
    const action = target.status === 'FORCE_CHANGE_PASSWORD' ? 'resend the invitation' : 'send a password-reset email';
    if (!window.confirm(`Would you like to ${action} to ${target.email}?`)) return;
    setError('');
    setMessage('');
    try {
      const result = await api<{ action: string }>(`/admin/users/${encodeURIComponent(target.username)}/reset-password`, { method: 'POST' });
      setMessage(result.action === 'invitation_resent'
        ? `A new generated temporary password was emailed to ${target.email}.`
        : `A password-reset code was emailed to ${target.email}.`);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to send password reset');
    }
  }

  async function remove(target: AdminUser) {
    if (!window.confirm(`Delete ${target.email}? The account and its GovVue data will be removed.`)) return;
    setError('');
    setMessage('');
    try {
      await api(`/admin/users/${encodeURIComponent(target.username)}`, { method: 'DELETE' });
      setMessage(`Deleted ${target.email}.`);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to delete user');
    }
  }

  if (currentUser?.role !== 'admin') return <div className="usa-alert usa-alert--error"><div className="usa-alert__body"><p className="usa-alert__text">Administrator role is required.</p></div></div>;

  return (
    <>
      <div className="page-heading"><div><p className="page-kicker">Administration</p><h1>Manage users</h1></div></div>
      <form className="search-panel admin-create-user" onSubmit={create}>
        <h2>Add user</h2>
        <p className="text-base">Cognito generates and emails a temporary password. The user must replace it during first sign-in.</p>
        <div className="grid-row grid-gap">
          <div className="tablet:grid-col-8">
            <label className="usa-label" htmlFor="admin-new-email">Email</label>
            <input className="usa-input maxw-none" id="admin-new-email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
          </div>
          <div className="tablet:grid-col-4">
            <label className="usa-label" htmlFor="admin-new-role">Role</label>
            <select className="usa-select maxw-none" id="admin-new-role" value={role} onChange={(event) => setRole(event.target.value as 'user' | 'admin')}>
              <option value="user">User</option>
              <option value="admin">Administrator</option>
            </select>
          </div>
        </div>
        <button className="usa-button margin-top-3" type="submit" disabled={creating}>{creating ? 'Creating…' : 'Add user and send invitation'}</button>
      </form>

      <form className="search-panel admin-create-company" onSubmit={createCompany}>
        <h2>Company workspaces</h2>
        <p className="text-base">A company has one shared profile and can include many users.</p>
        <div className="admin-create-company__controls">
          <div>
            <label className="usa-label" htmlFor="admin-company-name">Company name</label>
            <input className="usa-input maxw-none" id="admin-company-name" required value={companyName} onChange={(event) => setCompanyName(event.target.value)} />
          </div>
          <button className="usa-button" type="submit" disabled={creatingCompany}>{creatingCompany ? 'Creating…' : 'Create company'}</button>
        </div>
      </form>

      {error && <Alert type="error">{error}</Alert>}
      {message && <Alert type="success">{message}</Alert>}

      <section className="results-section">
        <div className="section-heading"><h2>Users</h2><button className="usa-button usa-button--unstyled" type="button" disabled={loading} onClick={load}>Refresh</button></div>
        {loading ? <p>Loading users…</p> : (
          <div className="admin-user-list">
            {users.map((item) => (
              <AdminUserCard
                key={item.username}
                user={item}
                isCurrent={item.username === currentUser.username || item.sub === currentUser.username}
                companies={companies}
                update={update}
                updateAccess={updateAccess}
                sendReset={sendReset}
                remove={remove}
              />
            ))}
          </div>
        )}
      </section>
    </>
  );
}

function AdminUserCard({ user, isCurrent, companies, update, updateAccess, sendReset, remove }: {
  user: AdminUser;
  isCurrent: boolean;
  companies: Company[];
  update: (username: string, role: 'user' | 'admin', enabled: boolean) => Promise<void>;
  updateAccess: (username: string, companyId: string, companyRole: 'manager' | 'member', features: string[]) => Promise<void>;
  sendReset: (user: AdminUser) => Promise<void>;
  remove: (user: AdminUser) => Promise<void>;
}) {
  const [role, setRole] = useState(user.role);
  const [enabled, setEnabled] = useState(user.enabled);
  const [saving, setSaving] = useState(false);
  const [companyId, setCompanyId] = useState(user.company_id || '');
  const [companyRole, setCompanyRole] = useState<'manager' | 'member'>(user.company_role || 'member');
  const [aiSearch, setAiSearch] = useState(user.features?.includes('natural_language_search') || false);
  const [savingAccess, setSavingAccess] = useState(false);

  useEffect(() => {
    setRole(user.role);
    setEnabled(user.enabled);
    setCompanyId(user.company_id || '');
    setCompanyRole(user.company_role || 'member');
    setAiSearch(user.features?.includes('natural_language_search') || false);
  }, [user.role, user.enabled, user.company_id, user.company_role, user.features]);

  async function save() {
    setSaving(true);
    try { await update(user.username, role, enabled); } finally { setSaving(false); }
  }

  async function saveAccess() {
    setSavingAccess(true);
    try {
      await updateAccess(user.username, companyId, companyRole, aiSearch ? ['natural_language_search'] : []);
    } finally {
      setSavingAccess(false);
    }
  }

  const accessChanged = companyId !== (user.company_id || '')
    || companyRole !== (user.company_role || 'member')
    || aiSearch !== (user.features?.includes('natural_language_search') || false);

  return (
    <article className="admin-user-card">
      <div className="admin-user-card__heading">
        <div><h3>{user.email || user.username}</h3><p>{user.status.replaceAll('_', ' ').toLocaleLowerCase()}{isCurrent ? ' · your account' : ''}</p></div>
        <span className={`status-pill ${user.enabled ? 'status-pill--enabled' : ''}`}>{user.enabled ? 'Enabled' : 'Disabled'}</span>
      </div>
      <div className="admin-user-card__controls">
        <div>
          <label className="usa-label" htmlFor={`role-${user.username}`}>Role</label>
          <select className="usa-select" id={`role-${user.username}`} value={role} disabled={isCurrent} onChange={(event) => setRole(event.target.value as 'user' | 'admin')}>
            <option value="user">User</option>
            <option value="admin">Administrator</option>
          </select>
        </div>
        <div className="admin-user-card__enabled usa-checkbox">
          <input className="usa-checkbox__input" id={`enabled-${user.username}`} type="checkbox" checked={enabled} disabled={isCurrent} onChange={(event) => setEnabled(event.target.checked)} />
          <label className="usa-checkbox__label" htmlFor={`enabled-${user.username}`}>Account enabled</label>
        </div>
      </div>
      <fieldset className="usa-fieldset admin-user-card__access">
        <legend className="usa-legend">Company and features</legend>
        <div className="admin-user-card__access-grid">
          <div>
            <label className="usa-label" htmlFor={`company-${user.username}`}>Company</label>
            <select className="usa-select maxw-none" id={`company-${user.username}`} value={companyId} onChange={(event) => setCompanyId(event.target.value)}>
              <option value="">Not assigned</option>
              {companies.map((company) => <option key={company.company_id} value={company.company_id}>{company.name}</option>)}
            </select>
          </div>
          <div>
            <label className="usa-label" htmlFor={`company-role-${user.username}`}>Company role</label>
            <select className="usa-select maxw-none" id={`company-role-${user.username}`} value={companyRole} disabled={!companyId} onChange={(event) => setCompanyRole(event.target.value as 'manager' | 'member')}>
              <option value="member">Member</option>
              <option value="manager">Manager</option>
            </select>
          </div>
          <div className="usa-checkbox admin-user-card__feature">
            <input className="usa-checkbox__input" id={`feature-ai-${user.username}`} type="checkbox" checked={aiSearch} onChange={(event) => setAiSearch(event.target.checked)} />
            <label className="usa-checkbox__label" htmlFor={`feature-ai-${user.username}`}>AI natural-language search builder</label>
          </div>
        </div>
        <button className="usa-button usa-button--outline margin-top-2" type="button" disabled={savingAccess || !accessChanged} onClick={saveAccess}>{savingAccess ? 'Saving…' : 'Save company access'}</button>
      </fieldset>
      <div className="admin-user-card__actions">
        <button className="usa-button" type="button" disabled={isCurrent || saving || (role === user.role && enabled === user.enabled)} onClick={save}>{saving ? 'Saving…' : 'Save changes'}</button>
        <button className="usa-button usa-button--outline" type="button" disabled={isCurrent} onClick={() => sendReset(user)}>{user.status === 'FORCE_CHANGE_PASSWORD' ? 'Resend invitation' : 'Send password reset'}</button>
        <button className="usa-button usa-button--unstyled text-secondary-dark" type="button" disabled={isCurrent} onClick={() => remove(user)}>Delete user</button>
      </div>
    </article>
  );
}

function Alert({ type, children }: { type: 'error' | 'success'; children: string }) {
  return <div className={`usa-alert usa-alert--${type} margin-top-3`} role={type === 'error' ? 'alert' : 'status'}><div className="usa-alert__body"><p className="usa-alert__text">{children}</p></div></div>;
}
