import { useEffect, useMemo, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { api } from '../lib/api';
import type { AdminCompany, AdminUser } from '../types';

type Directory = { users: AdminUser[]; companies: AdminCompany[]; loading: boolean; error: string; reload: () => Promise<void> };
type PageSize = 10 | 25 | 50;

function useDirectory(): Directory {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [companies, setCompanies] = useState<AdminCompany[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  async function reload() {
    setLoading(true);
    try {
      const [userResponse, companyResponse] = await Promise.all([
        api<{ items: AdminUser[] }>('/admin/users'),
        api<{ items: AdminCompany[] }>('/admin/companies'),
      ]);
      setUsers(userResponse.items);
      setCompanies(companyResponse.items);
      setError('');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load the directory');
    } finally { setLoading(false); }
  }
  useEffect(() => { void reload(); }, []);
  return { users, companies, loading, error, reload };
}

function Notice({ error, message }: { error?: string; message?: string }) {
  return <>
    {error && <div className="alert alert-danger" role="alert">{error}</div>}
    {message && <div className="alert alert-success" role="status">{message}</div>}
  </>;
}

function PageHeader({ pretitle, title, back, action }: { pretitle: string; title: string; back?: string; action?: ReactNode }) {
  return <div className="page-header d-print-none mb-3"><div className="row align-items-center">
    <div className="col">
      {back && <Link className="small" to={back}>← Back to {back.includes('companies') ? 'companies' : 'users'}</Link>}
      <div className="page-pretitle">{pretitle}</div><h1 className="page-title">{title}</h1>
    </div>
    {action && <div className="col-auto ms-auto">{action}</div>}
  </div></div>;
}

function Pager({ count, page, size, onPage, onSize }: { count: number; page: number; size: PageSize; onPage: (page: number) => void; onSize: (size: PageSize) => void }) {
  const pages = Math.max(1, Math.ceil(count / size));
  const current = Math.min(page, pages);
  return <div className="card-footer admin-directory-pager">
    <span className="text-secondary">{count ? `${(current - 1) * size + 1}–${Math.min(current * size, count)} of ${count}` : '0 results'}</span>
    <div className="admin-directory-pager__controls">
      <label className="d-flex align-items-center gap-2">Rows <select className="form-select form-select-sm" aria-label="Rows per page" value={size} onChange={(event) => { onSize(Number(event.target.value) as PageSize); onPage(1); }}>
        <option value={10}>10</option><option value={25}>25</option><option value={50}>50</option>
      </select></label>
      <button className="btn btn-sm btn-outline-secondary" type="button" disabled={current <= 1} onClick={() => onPage(current - 1)}>Previous</button>
      <span aria-live="polite">Page {current} of {pages}</span>
      <button className="btn btn-sm btn-outline-secondary" type="button" disabled={current >= pages} onClick={() => onPage(current + 1)}>Next</button>
    </div>
  </div>;
}

function UserTable({ users, companies, companyId }: { users: AdminUser[]; companies: AdminCompany[]; companyId?: string }) {
  const [query, setQuery] = useState('');
  const [role, setRole] = useState('all');
  const [status, setStatus] = useState('all');
  const [company, setCompany] = useState('all');
  const [companyRole, setCompanyRole] = useState('all');
  const [sort, setSort] = useState('email-asc');
  const [page, setPage] = useState(1);
  const [size, setSize] = useState<PageSize>(10);
  const filtered = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    return users.filter((user) =>
      (!companyId || user.company_id === companyId)
      && (!term || [user.email, user.username, user.company_name].some((value) => value?.toLocaleLowerCase().includes(term)))
      && (role === 'all' || user.role === role)
      && (status === 'all' || (status === 'enabled' ? user.enabled : status === 'disabled' ? !user.enabled : user.status === status))
      && (companyId || company === 'all' || (company === 'none' ? !user.company_id : user.company_id === company))
      && (companyRole === 'all' || (companyRole === 'none' ? !user.company_id : user.company_id && user.company_role === companyRole))
    ).sort((a, b) => {
      const [field, direction] = sort.split('-');
      const left = field === 'company' ? a.company_name : field === 'created' ? a.created_at : a.email || a.username;
      const right = field === 'company' ? b.company_name : field === 'created' ? b.created_at : b.email || b.username;
      return left.localeCompare(right, undefined, { sensitivity: 'base', numeric: true }) * (direction === 'desc' ? -1 : 1);
    });
  }, [users, companyId, query, role, status, company, companyRole, sort]);
  const current = Math.min(page, Math.max(1, Math.ceil(filtered.length / size)));
  const visible = filtered.slice((current - 1) * size, current * size);
  function resetPage(setter: (value: string) => void, value: string) { setter(value); setPage(1); }
  return <div className="card">
    <div className="card-body admin-directory-filters">
      <label>Search users<input className="form-control" type="search" placeholder="Email, username, or company" value={query} onChange={(event) => resetPage(setQuery, event.target.value)} /></label>
      <label>GovVue role<select className="form-select" value={role} onChange={(event) => resetPage(setRole, event.target.value)}><option value="all">All roles</option><option value="admin">Administrators</option><option value="user">Users</option></select></label>
      <label>Account<select className="form-select" value={status} onChange={(event) => resetPage(setStatus, event.target.value)}><option value="all">All statuses</option><option value="enabled">Enabled</option><option value="disabled">Disabled</option><option value="FORCE_CHANGE_PASSWORD">Invitation pending</option><option value="CONFIRMED">Confirmed</option></select></label>
      {!companyId && <label>Company<select className="form-select" value={company} onChange={(event) => resetPage(setCompany, event.target.value)}><option value="all">All companies</option><option value="none">Unassigned</option>{companies.map((item) => <option value={item.company_id} key={item.company_id}>{item.name}</option>)}</select></label>}
      <label>Company role<select className="form-select" value={companyRole} onChange={(event) => resetPage(setCompanyRole, event.target.value)}><option value="all">All company roles</option><option value="manager">Managers</option><option value="member">Members</option>{!companyId && <option value="none">Unassigned</option>}</select></label>
      <label>Sort<select className="form-select" value={sort} onChange={(event) => resetPage(setSort, event.target.value)}><option value="email-asc">Email A–Z</option><option value="email-desc">Email Z–A</option><option value="created-desc">Newest first</option><option value="created-asc">Oldest first</option><option value="company-asc">Company A–Z</option></select></label>
    </div>
    <div className="table-responsive"><table className="table table-vcenter card-table admin-directory-table"><thead><tr><th>User</th><th>GovVue role</th>{!companyId && <th>Company</th>}<th>Company role</th><th>Status</th><th className="w-1">Manage</th></tr></thead><tbody>
      {visible.map((user) => <tr key={user.username}><td><Link className="fw-semibold" to={`/admin/users/${encodeURIComponent(user.username)}`}>{user.email || user.username}</Link>{user.email && user.email !== user.username && <div className="text-secondary small">{user.username}</div>}</td>
        <td>{user.role === 'admin' ? 'Administrator' : 'User'}</td>{!companyId && <td>{user.company_name || <span className="text-secondary">Unassigned</span>}</td>}
        <td>{user.company_id ? (user.company_role === 'manager' ? 'Manager' : 'Member') : '—'}</td>
        <td><span className={`badge ${user.enabled ? 'bg-success-lt' : 'bg-secondary-lt'}`}>{user.enabled ? 'Enabled' : 'Disabled'}</span></td>
        <td><Link className="btn btn-sm btn-outline-primary" to={`/admin/users/${encodeURIComponent(user.username)}`} aria-label={`Manage ${user.email || user.username}`}>Manage</Link></td></tr>)}
      {!visible.length && <tr><td colSpan={companyId ? 5 : 6} className="text-secondary text-center py-4">No users match these filters.</td></tr>}
    </tbody></table></div>
    <Pager count={filtered.length} page={current} size={size} onPage={setPage} onSize={setSize} />
  </div>;
}

export function AdminUsersList() {
  const directory = useDirectory();
  const [adding, setAdding] = useState(false);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<'user' | 'admin'>('user');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  async function create(event: FormEvent) {
    event.preventDefault(); setCreating(true); setError(''); setMessage('');
    try {
      const created = await api<AdminUser>('/admin/users', { method: 'POST', body: JSON.stringify({ email, role }) });
      setEmail(''); setRole('user'); setAdding(false);
      setMessage(`Created ${created.email}. Cognito emailed a generated temporary password.${created.ses_status === 'verified' ? ' The recipient is verified in SES.' : created.ses_status === 'verification_requested' ? ' SES recipient verification was requested for daily emails while the account is sandboxed.' : ''}`);
      await directory.reload();
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to create user'); }
    finally { setCreating(false); }
  }
  return <>
    <PageHeader pretitle="Administration" title="Users" action={<div className="d-flex gap-2"><button className="btn btn-outline-secondary" onClick={() => void directory.reload()}>Refresh</button><button className="btn btn-primary" onClick={() => setAdding(!adding)}>{adding ? 'Cancel' : 'Add user'}</button></div>} />
    <Notice error={error || directory.error} message={message} />
    {adding && <form className="card mb-3" onSubmit={create}><div className="card-header"><h2 className="card-title">Invite user</h2></div><div className="card-body"><p className="text-secondary">Cognito generates and emails a temporary password.</p><div className="row g-3"><label className="col-md-8">Email<input className="form-control" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label><label className="col-md-4">GovVue role<select className="form-select" value={role} onChange={(event) => setRole(event.target.value as 'user' | 'admin')}><option value="user">User</option><option value="admin">Administrator</option></select></label></div></div><div className="card-footer"><button className="btn btn-primary" disabled={creating}>{creating ? 'Creating…' : 'Add user and send invitation'}</button></div></form>}
    {directory.loading ? <p>Loading users…</p> : <UserTable users={directory.users} companies={directory.companies} />}
  </>;
}

export function AdminUserDetail() {
  const { username = '' } = useParams();
  const navigate = useNavigate();
  const { user: currentUser } = useAuth();
  const directory = useDirectory();
  const user = directory.users.find((item) => item.username === username);
  const isCurrent = !!user && (user.username === currentUser?.username || user.sub === currentUser?.username);
  const [role, setRole] = useState<'user' | 'admin'>('user');
  const [enabled, setEnabled] = useState(true);
  const [companyId, setCompanyId] = useState('');
  const [companyRole, setCompanyRole] = useState<'manager' | 'member'>('member');
  const [aiSearch, setAiSearch] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  useEffect(() => {
    if (!user) return;
    setRole(user.role); setEnabled(user.enabled); setCompanyId(user.company_id || '');
    setCompanyRole(user.company_role || 'member'); setAiSearch(user.features?.includes('natural_language_search') || false);
  }, [user]);
  async function act(action: () => Promise<void>, success: string) {
    setSaving(true); setError(''); setMessage('');
    try { await action(); setMessage(success); await directory.reload(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to update user'); }
    finally { setSaving(false); }
  }
  async function remove() {
    if (!user || !window.confirm(`Delete ${user.email}? The account and its GovVue data will be removed.`)) return;
    setSaving(true); setError('');
    try { await api(`/admin/users/${encodeURIComponent(user.username)}`, { method: 'DELETE' }); navigate('/admin/users', { replace: true }); }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to delete user'); setSaving(false); }
  }
  if (directory.loading) return <p>Loading user…</p>;
  if (!user) return <><PageHeader pretitle="Administration" title="User not found" back="/admin/users" /><Notice error={directory.error || 'This user no longer exists.'} /></>;
  const accessChanged = companyId !== (user.company_id || '') || companyRole !== (user.company_role || 'member') || aiSearch !== (user.features?.includes('natural_language_search') || false);
  return <>
    <PageHeader pretitle="User details" title={user.email || user.username} back="/admin/users" />
    <Notice error={error || directory.error} message={message} />
    {isCurrent && <div className="alert alert-info">Use Account in the main app to change your own password. Your GovVue role and enabled status cannot be changed here.</div>}
    <div className="row row-cards">
      <div className="col-lg-6"><section className="card h-100"><div className="card-header"><h2 className="card-title">Account</h2></div><div className="card-body">
        <dl className="admin-detail-list"><div><dt>Username</dt><dd>{user.username}</dd></div><div><dt>Cognito status</dt><dd>{user.status.replaceAll('_', ' ').toLocaleLowerCase()}</dd></div><div><dt>Created</dt><dd>{user.created_at ? new Date(user.created_at).toLocaleString() : '—'}</dd></div><div><dt>Email verified</dt><dd>{user.email_verified ? 'Yes' : 'No'}</dd></div></dl>
        <label className="form-label" htmlFor="detail-role">GovVue role</label><select className="form-select mb-3" id="detail-role" value={role} disabled={isCurrent} onChange={(event) => setRole(event.target.value as 'user' | 'admin')}><option value="user">User</option><option value="admin">Administrator</option></select>
        <label className="form-check"><input className="form-check-input" type="checkbox" checked={enabled} disabled={isCurrent} onChange={(event) => setEnabled(event.target.checked)} /><span className="form-check-label">Account enabled</span></label>
      </div><div className="card-footer"><button className="btn btn-primary" disabled={saving || isCurrent || (role === user.role && enabled === user.enabled)} onClick={() => void act(() => api(`/admin/users/${encodeURIComponent(user.username)}`, { method: 'PUT', body: JSON.stringify({ role, enabled }) }), 'Account updated. Role changes appear after the user refreshes or signs in again.')}>Save account</button></div></section></div>
      <div className="col-lg-6"><section className="card h-100"><div className="card-header"><h2 className="card-title">Company and features</h2></div><div className="card-body">
        <label className="form-label" htmlFor="detail-company">Company</label><select className="form-select mb-3" id="detail-company" value={companyId} onChange={(event) => setCompanyId(event.target.value)}><option value="">Not assigned</option>{directory.companies.map((company) => <option key={company.company_id} value={company.company_id}>{company.name}</option>)}</select>
        <label className="form-label" htmlFor="detail-company-role">Company role</label><select className="form-select mb-3" id="detail-company-role" value={companyRole} disabled={!companyId} onChange={(event) => setCompanyRole(event.target.value as 'manager' | 'member')}><option value="member">Member</option><option value="manager">Manager</option></select>
        <label className="form-check"><input className="form-check-input" type="checkbox" checked={aiSearch} onChange={(event) => setAiSearch(event.target.checked)} /><span className="form-check-label">AI natural-language search builder</span></label>
      </div><div className="card-footer"><button className="btn btn-primary" disabled={saving || !accessChanged} onClick={() => void act(() => api(`/admin/users/${encodeURIComponent(user.username)}/access`, { method: 'PUT', body: JSON.stringify({ company_id: companyId, company_role: companyRole, features: aiSearch ? ['natural_language_search'] : [] }) }), 'Company access and features updated.')}>Save access</button></div></section></div>
    </div>
    <div className="card mt-3"><div className="card-header"><h2 className="card-title">Other actions</h2></div><div className="card-body d-flex flex-wrap gap-2">
      <button className="btn btn-outline-primary" disabled={saving || isCurrent} onClick={() => { if (window.confirm(`${user.status === 'FORCE_CHANGE_PASSWORD' ? 'Resend the invitation' : 'Send a password-reset email'} to ${user.email}?`)) void act(async () => { await api(`/admin/users/${encodeURIComponent(user.username)}/reset-password`, { method: 'POST' }); }, user.status === 'FORCE_CHANGE_PASSWORD' ? `A new generated temporary password was emailed to ${user.email}.` : `A password-reset code was emailed to ${user.email}.`); }}>{user.status === 'FORCE_CHANGE_PASSWORD' ? 'Resend invitation' : 'Send password reset'}</button>
      <button className="btn btn-outline-danger" disabled={saving || isCurrent} onClick={() => void remove()}>Delete user</button>
    </div></div>
  </>;
}

export function AdminCompaniesList() {
  const directory = useDirectory();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const [manager, setManager] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [query, setQuery] = useState('');
  const [membership, setMembership] = useState('all');
  const [managerFilter, setManagerFilter] = useState('all');
  const [sort, setSort] = useState('name-asc');
  const [page, setPage] = useState(1);
  const [size, setSize] = useState<PageSize>(10);
  const filtered = useMemo(() => directory.companies.filter((company) =>
    (!query.trim() || [company.name, ...company.managers.map((item) => item.email)].some((value) => value.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())))
    && (membership === 'all' || (membership === 'with' ? company.member_count > 0 : company.member_count === 0))
    && (managerFilter === 'all' || (managerFilter === 'assigned' ? company.managers.length > 0 : company.managers.length === 0))
  ).sort((a, b) => {
    const [field, direction] = sort.split('-');
    const comparison = field === 'members' ? a.member_count - b.member_count : a.name.localeCompare(b.name, undefined, { sensitivity: 'base' });
    return comparison * (direction === 'desc' ? -1 : 1);
  }), [directory.companies, query, membership, managerFilter, sort]);
  const current = Math.min(page, Math.max(1, Math.ceil(filtered.length / size)));
  const visible = filtered.slice((current - 1) * size, current * size);
  async function create(event: FormEvent) {
    event.preventDefault(); setCreating(true); setError(''); setMessage('');
    try {
      const created = await api<AdminCompany>('/admin/companies', { method: 'POST', body: JSON.stringify({ name, manager_username: manager }) });
      setName(''); setManager(''); setAdding(false); setMessage(`Created ${created.name} and assigned its initial company manager.`);
      await directory.reload();
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to create company'); }
    finally { setCreating(false); }
  }
  return <>
    <PageHeader pretitle="Administration" title="Companies" action={<div className="d-flex gap-2"><button className="btn btn-outline-secondary" onClick={() => void directory.reload()}>Refresh</button><button className="btn btn-primary" onClick={() => setAdding(!adding)}>{adding ? 'Cancel' : 'Create company'}</button></div>} />
    <Notice error={error || directory.error} message={message} />
    {adding && <form className="card mb-3" onSubmit={create}><div className="card-header"><h2 className="card-title">Create company workspace</h2></div><div className="card-body"><p className="text-secondary">Creates a blank shared profile and assigns an existing unassigned user as manager.</p><div className="row g-3"><label className="col-md-6">Company name<input className="form-control" required value={name} onChange={(event) => setName(event.target.value)} /></label><label className="col-md-6">Initial manager<select className="form-select" required value={manager} onChange={(event) => setManager(event.target.value)}><option value="">Select an unassigned user</option>{directory.users.filter((user) => !user.company_id && user.enabled).map((user) => <option key={user.username} value={user.username}>{user.email || user.username}</option>)}</select></label></div></div><div className="card-footer"><button className="btn btn-primary" disabled={creating || !manager}>{creating ? 'Creating…' : 'Create company and profile'}</button></div></form>}
    {directory.loading ? <p>Loading companies…</p> : <div className="card">
      <div className="card-body admin-directory-filters"><label>Search companies<input className="form-control" type="search" placeholder="Name or manager email" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} /></label><label>Members<select className="form-select" value={membership} onChange={(event) => { setMembership(event.target.value); setPage(1); }}><option value="all">All companies</option><option value="with">Has members</option><option value="without">No members</option></select></label><label>Manager<select className="form-select" value={managerFilter} onChange={(event) => { setManagerFilter(event.target.value); setPage(1); }}><option value="all">Any manager status</option><option value="assigned">Has manager</option><option value="unassigned">No manager</option></select></label><label>Sort<select className="form-select" value={sort} onChange={(event) => { setSort(event.target.value); setPage(1); }}><option value="name-asc">Name A–Z</option><option value="name-desc">Name Z–A</option><option value="members-desc">Most members</option><option value="members-asc">Fewest members</option></select></label></div>
      <div className="table-responsive"><table className="table table-vcenter card-table admin-directory-table"><thead><tr><th>Company</th><th>Members</th><th>Managers</th><th className="w-1">Manage</th></tr></thead><tbody>
        {visible.map((company) => <tr key={company.company_id}><td><Link className="fw-semibold" to={`/admin/companies/${company.company_id}`}>{company.name}</Link></td><td>{company.member_count}</td><td>{company.managers.map((item) => item.email || item.username).join(', ') || <span className="text-secondary">None designated</span>}</td><td><Link className="btn btn-sm btn-outline-primary" to={`/admin/companies/${company.company_id}`} aria-label={`Manage ${company.name}`}>Manage</Link></td></tr>)}
        {!visible.length && <tr><td colSpan={4} className="text-secondary text-center py-4">No companies match these filters.</td></tr>}
      </tbody></table></div><Pager count={filtered.length} page={current} size={size} onPage={setPage} onSize={setSize} />
    </div>}
  </>;
}

export function AdminCompanyDetail() {
  const { companyId = '' } = useParams();
  const directory = useDirectory();
  const company = directory.companies.find((item) => item.company_id === companyId);
  if (directory.loading) return <p>Loading company…</p>;
  if (!company) return <><PageHeader pretitle="Administration" title="Company not found" back="/admin/companies" /><Notice error={directory.error || 'This company no longer exists.'} /></>;
  return <>
    <PageHeader pretitle="Company details" title={company.name} back="/admin/companies" action={<Link className="btn btn-primary" to={`/admin/companies/${company.company_id}/profile`}>Manage profile</Link>} />
    <Notice error={directory.error} />
    <div className="card mb-3"><div className="card-body"><div className="row"><div className="col-sm-4"><div className="subheader">Members</div><div className="h2 mb-0">{company.member_count}</div></div><div className="col-sm-8"><div className="subheader">Managers</div><div>{company.managers.map((item) => item.email || item.username).join(', ') || 'None designated'}</div></div></div></div></div>
    <div className="d-flex justify-content-between align-items-center mb-2"><h2 className="h3 mb-0">Company users</h2><Link className="btn btn-outline-primary" to="/admin/users">Manage all users</Link></div>
    <UserTable users={directory.users} companies={directory.companies} companyId={companyId} />
  </>;
}
