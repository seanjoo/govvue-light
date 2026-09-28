import { FormEvent, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { api } from '../lib/api';
import type { CompanyMember, CompanyProfile, CompanyProfileResponse } from '../types';

const EMPTY_PROFILE: CompanyProfile = {
  overview: '',
  capabilities: '',
  differentiators: '',
  past_performance: '',
  naics_codes: '',
  psc_codes: '',
  target_agencies: '',
  set_aside_eligibility: '',
  positive_keywords: '',
  negative_keywords: '',
};

const FIELDS: Array<{ name: keyof CompanyProfile; label: string; hint: string; rows?: number }> = [
  { name: 'overview', label: 'Company overview', hint: 'What the company does, the customers it serves, and its core mission.', rows: 5 },
  { name: 'capabilities', label: 'Capabilities', hint: 'One capability per line. Include technologies, services, products, and delivery strengths.', rows: 6 },
  { name: 'differentiators', label: 'Differentiators', hint: 'Why the company is a strong or unusual fit.', rows: 4 },
  { name: 'past_performance', label: 'Past performance', hint: 'Relevant customers, contracts, programs, and outcomes. Do not include sensitive information.', rows: 5 },
  { name: 'naics_codes', label: 'NAICS codes', hint: 'Comma-separated six-digit codes.' },
  { name: 'psc_codes', label: 'PSC codes', hint: 'Comma-separated product or service codes.' },
  { name: 'target_agencies', label: 'Target agencies', hint: 'Comma-separated agencies or organizations.' },
  { name: 'set_aside_eligibility', label: 'Set-aside eligibility', hint: 'Examples: Small Business, WOSB, 8(a), HUBZone, SDVOSB.' },
  { name: 'positive_keywords', label: 'Preferred keywords', hint: 'Terms that usually indicate a good opportunity.' },
  { name: 'negative_keywords', label: 'Exclusions', hint: 'Work, products, or terms the company does not pursue.' },
];

export default function CompanyProfilePage() {
  const { companyId } = useParams();
  const { user } = useAuth();
  const endpoint = companyId ? `/admin/companies/${encodeURIComponent(companyId)}/profile` : '/company-profile';
  const [data, setData] = useState<CompanyProfileResponse | null>(null);
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [companyName, setCompanyName] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [members, setMembers] = useState<CompanyMember[]>([]);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<'manager' | 'member'>('member');
  const [inviting, setInviting] = useState(false);

  async function loadMembers() {
    const response = await api<{ items: CompanyMember[] }>('/company-members');
    setMembers(response.items);
  }

  useEffect(() => {
    api<CompanyProfileResponse>(endpoint)
      .then((response) => {
        setData(response);
        setProfile(response.profile);
        if (response.can_edit && !companyId) loadMembers().catch((caught) => setError(caught instanceof Error ? caught.message : 'Unable to load company members'));
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Unable to load company profile'))
      .finally(() => setLoading(false));
  }, [companyId, endpoint]);

  async function createCompany(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await api<CompanyProfileResponse>('/company-profile', {
        method: 'POST',
        body: JSON.stringify({ name: companyName, profile }),
      });
      setData(response);
      setProfile(response.profile);
      setCompanyName('');
      setMessage(`Created ${response.company?.name}. You are now its company administrator.`);
      await loadMembers();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to create company profile');
    } finally {
      setSaving(false);
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const response = await api<CompanyProfileResponse>(endpoint, {
        method: 'PUT',
        body: JSON.stringify({ profile }),
      });
      setData(response);
      setProfile(response.profile);
      setMessage('Company profile saved. New AI search plans can use these details.');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to save company profile');
    } finally {
      setSaving(false);
    }
  }

  async function invite(event: FormEvent) {
    event.preventDefault();
    setInviting(true);
    setError('');
    setMessage('');
    try {
      const created = await api<CompanyMember>('/company-members', {
        method: 'POST',
        body: JSON.stringify({ email: inviteEmail, company_role: inviteRole }),
      });
      setInviteEmail('');
      setInviteRole('member');
      setMessage(`Invited ${created.email}. Cognito emailed a generated temporary password.`);
      await loadMembers();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to invite company member');
    } finally {
      setInviting(false);
    }
  }

  async function changeMemberRole(member: CompanyMember, companyRole: 'manager' | 'member') {
    setError('');
    setMessage('');
    try {
      await api(`/company-members/${encodeURIComponent(member.username)}`, {
        method: 'PUT',
        body: JSON.stringify({ company_role: companyRole }),
      });
      setMessage(`Updated ${member.email}.`);
      await loadMembers();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to update company member');
    }
  }

  async function removeMember(member: CompanyMember) {
    if (!window.confirm(`Remove ${member.email} from this company? Their GovVue Light account and personal data will remain.`)) return;
    setError('');
    setMessage('');
    try {
      await api(`/company-members/${encodeURIComponent(member.username)}`, { method: 'DELETE' });
      setMessage(`Removed ${member.email} from the company.`);
      await loadMembers();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to remove company member');
    }
  }

  if (loading) return <p>Loading company profile…</p>;
  return (
    <>
      <div className="page-heading">
        <div><p className="page-kicker">Company workspace</p><h1>{data?.company?.name || (data?.can_create ? 'Create your company profile' : 'Company profile')}</h1></div>
        {companyId && <Link className="usa-button usa-button--outline" to="/admin/users">Back to admin</Link>}
      </div>
      {error && <Alert type="error">{error}</Alert>}
      {message && <Alert type="success">{message}</Alert>}
      {data?.can_create && (
        <form className="search-panel company-profile" onSubmit={createCompany}>
          <h2 className="margin-top-0">Set up your company workspace</h2>
          <p className="text-base">Your account is not linked to a company. Create the shared company profile below and you will become its company administrator, with permission to maintain the profile and invite members. This does not grant GovVue platform-administrator access.</p>
          <div className="margin-bottom-3">
            <label className="usa-label" htmlFor="profile-company-name">Company name</label>
            <span className="usa-hint">Use the organization name that other invited users will recognize.</span>
            <input className="usa-input maxw-none" id="profile-company-name" required minLength={2} maxLength={120} value={companyName} onChange={(event) => setCompanyName(event.target.value)} />
          </div>
          <ProfileFields profile={profile} onChange={(name, value) => setProfile((current) => ({ ...current, [name]: value }))} />
          <button className="usa-button margin-top-3" type="submit" disabled={saving}>{saving ? 'Creating…' : 'Create company profile'}</button>
        </form>
      )}
      {data?.company && (
        <form className="search-panel company-profile" onSubmit={save}>
          <p className="text-base margin-top-0">This profile is shared by everyone assigned to {data.company.name}. The AI search builder uses it only when requested or when an automatic search refers to company fit.</p>
          {!data.can_edit && <p className="usa-hint">You can view this profile. A company manager or administrator can edit it.</p>}
          <ProfileFields profile={profile} disabled={!data.can_edit} onChange={(name, value) => setProfile((current) => ({ ...current, [name]: value }))} />
          {data.can_edit && <button className="usa-button margin-top-3" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save company profile'}</button>}
        </form>
      )}
      {data?.company && data.can_edit && !companyId && (
        <section className="search-panel company-members">
          <div className="section-heading"><div><p className="page-kicker">Company access</p><h2>Members</h2></div></div>
          <form className="company-members__invite" onSubmit={invite}>
            <div>
              <label className="usa-label" htmlFor="company-invite-email">Email address</label>
              <input className="usa-input maxw-none" id="company-invite-email" type="email" required value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} />
            </div>
            <div>
              <label className="usa-label" htmlFor="company-invite-role">Company role</label>
              <select className="usa-select maxw-none" id="company-invite-role" value={inviteRole} onChange={(event) => setInviteRole(event.target.value as 'manager' | 'member')}>
                <option value="member">Member</option>
                <option value="manager">Manager</option>
              </select>
            </div>
            <button className="usa-button" type="submit" disabled={inviting}>{inviting ? 'Sending invitation…' : 'Invite member'}</button>
          </form>
          <p className="usa-hint">Invited users receive GovVue Light’s standard temporary-password email. Removing a member only removes company access.</p>
          <div className="company-members__list">
            {members.map((member) => {
              const isCurrent = member.username === user?.username || member.sub === user?.username;
              return (
                <article className="company-member" key={member.username}>
                  <div><strong>{member.email}</strong><span>{member.status.replaceAll('_', ' ').toLocaleLowerCase()}{isCurrent ? ' · you' : ''}</span></div>
                  <select className="usa-select" aria-label={`Company role for ${member.email}`} value={member.company_role} disabled={isCurrent} onChange={(event) => changeMemberRole(member, event.target.value as 'manager' | 'member')}>
                    <option value="member">Member</option>
                    <option value="manager">Manager</option>
                  </select>
                  <button className="usa-button usa-button--unstyled text-secondary-dark" type="button" disabled={isCurrent} onClick={() => removeMember(member)}>Remove</button>
                </article>
              );
            })}
          </div>
        </section>
      )}
    </>
  );
}

function ProfileFields({ profile, disabled = false, onChange }: {
  profile: CompanyProfile;
  disabled?: boolean;
  onChange: (name: keyof CompanyProfile, value: string) => void;
}) {
  return (
    <div className="company-profile__fields">
      {FIELDS.map((field) => (
        <div key={field.name}>
          <label className="usa-label" htmlFor={`profile-${field.name}`}>{field.label}</label>
          <span className="usa-hint">{field.hint}</span>
          {field.rows ? (
            <textarea className="usa-textarea maxw-none" id={`profile-${field.name}`} rows={field.rows} value={profile[field.name]} disabled={disabled} onChange={(event) => onChange(field.name, event.target.value)} />
          ) : (
            <input className="usa-input maxw-none" id={`profile-${field.name}`} value={profile[field.name]} disabled={disabled} onChange={(event) => onChange(field.name, event.target.value)} />
          )}
        </div>
      ))}
    </div>
  );
}

function Alert({ type, children }: { type: 'error' | 'success'; children: string }) {
  return <div className={`usa-alert usa-alert--${type} margin-bottom-3`} role={type === 'error' ? 'alert' : 'status'}><div className="usa-alert__body"><p className="usa-alert__text">{children}</p></div></div>;
}
