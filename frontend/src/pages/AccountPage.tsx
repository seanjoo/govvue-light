import { FormEvent, useState } from 'react';
import { useAuth } from '../auth/AuthProvider';
import { changePassword } from '../auth/cognito';

export default function AccountPage() {
  const { user } = useAuth();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setMessage('');
    if (newPassword !== confirmPassword) {
      setError('New passwords do not match.');
      return;
    }
    setSaving(true);
    try {
      await changePassword(currentPassword, newPassword);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setMessage('Your password was changed.');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to change password');
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="page-heading"><div><p className="page-kicker">Profile and security</p><h1>Account</h1></div></div>
      <section className="search-panel account-summary">
        <h2>Account details</h2>
        <dl className="detail-grid">
          <div><dt>Email</dt><dd>{user?.email}</dd></div>
          <div><dt>Role</dt><dd>{user?.role === 'admin' ? 'Administrator' : 'User'}</dd></div>
        </dl>
      </section>
      <section className="search-panel account-password-panel">
        <h2>Change password</h2>
        <p className="text-base">Use at least 12 characters with uppercase, lowercase, number, and symbol characters.</p>
        {error && <Alert type="error">{error}</Alert>}
        {message && <Alert type="success">{message}</Alert>}
        <form className="usa-form" onSubmit={submit}>
          <label className="usa-label" htmlFor="current-password">Current password</label>
          <input className="usa-input" id="current-password" type="password" autoComplete="current-password" required value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} />
          <label className="usa-label" htmlFor="new-password">New password</label>
          <input className="usa-input" id="new-password" type="password" autoComplete="new-password" minLength={12} required value={newPassword} onChange={(event) => setNewPassword(event.target.value)} />
          <label className="usa-label" htmlFor="confirm-password">Confirm new password</label>
          <input className="usa-input" id="confirm-password" type="password" autoComplete="new-password" minLength={12} required value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} />
          <button className="usa-button margin-top-3" type="submit" disabled={saving}>{saving ? 'Changing…' : 'Change password'}</button>
        </form>
      </section>
    </>
  );
}

function Alert({ type, children }: { type: 'error' | 'success'; children: string }) {
  return <div className={`usa-alert usa-alert--${type} margin-y-2`} role={type === 'error' ? 'alert' : 'status'}><div className="usa-alert__body"><p className="usa-alert__text">{children}</p></div></div>;
}
