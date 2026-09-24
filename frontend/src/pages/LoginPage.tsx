import { FormEvent, useEffect, useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import PasswordRequirements from '../components/PasswordRequirements';
import { beginPasswordReset, finishPasswordReset } from '../auth/cognito';
import { passwordMeetsPolicy } from '../lib/passwordPolicy';
import { runtimeConfig } from '../runtimeConfig';

export default function LoginPage() {
  const { user, loading, signIn, setNewPassword, signInWithGoogle } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [newPasswordRequired, setNewPasswordRequired] = useState(false);
  const [resetMode, setResetMode] = useState<'none' | 'request' | 'confirm'>('none');
  const [confirmationCode, setConfirmationCode] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [googleSubmitting, setGoogleSubmitting] = useState(false);

  const requestedPath = (() => {
    const from = (location.state as { from?: { pathname?: string; search?: string } } | null)?.from;
    const fromPath = from?.pathname ? `${from.pathname}${from.search || ''}` : '';
    const storedPath = window.sessionStorage.getItem('govvue.oauth.returnTo') || '';
    const candidate = fromPath || storedPath;
    return candidate.startsWith('/') && !candidate.startsWith('//') ? candidate : '/search';
  })();
  const creatingPassword = newPasswordRequired || resetMode === 'confirm';
  const passwordValid = passwordMeetsPolicy(password);
  const passwordsMatch = password.length > 0 && password === confirmPassword;

  useEffect(() => {
    if (!loading && user) window.sessionStorage.removeItem('govvue.oauth.returnTo');
  }, [loading, user]);

  if (!loading && user) return <Navigate to={requestedPath} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setMessage('');
    if (creatingPassword && !passwordValid) {
      setError('The new password does not meet all password requirements.');
      return;
    }
    if (creatingPassword && !passwordsMatch) {
      setError('New passwords do not match.');
      return;
    }
    setSubmitting(true);
    try {
      if (resetMode === 'request') {
        const result = await beginPasswordReset(email);
        if (result.nextStep.resetPasswordStep === 'CONFIRM_RESET_PASSWORD_WITH_CODE') {
          setResetMode('confirm');
          setMessage('A password-reset code was sent to your email address.');
        } else {
          setResetMode('none');
          setMessage('Your password reset is complete. You can sign in.');
        }
        return;
      }
      if (resetMode === 'confirm') {
        await finishPasswordReset(email, confirmationCode, password);
        setResetMode('none');
        setConfirmationCode('');
        setPassword('');
        setConfirmPassword('');
        setMessage('Your password was reset. Sign in with the new password.');
        return;
      }
      const result = newPasswordRequired
        ? await setNewPassword(password)
        : await signIn(email, password);
      if (result.isSignedIn) {
        navigate(requestedPath, { replace: true });
      } else if (result.nextStep.signInStep === 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED') {
        setPassword('');
        setConfirmPassword('');
        setNewPasswordRequired(true);
      } else {
        setError(`Additional Cognito step is required: ${result.nextStep.signInStep}`);
      }
    } catch (caught) {
      if (caught instanceof Error && caught.name === 'PasswordResetRequiredException') {
        setPassword('');
        setConfirmPassword('');
        setResetMode('confirm');
        setMessage('Enter the password-reset code from your email and choose a new password.');
      } else {
        setError(caught instanceof Error ? caught.message : 'Unable to sign in');
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function submitGoogle() {
    setError('');
    setMessage('');
    setGoogleSubmitting(true);
    try {
      await signInWithGoogle(requestedPath);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to start Google sign-in');
      setGoogleSubmitting(false);
    }
  }

  return (
    <main id="main-content" className="login-page">
      <div className="login-panel">
        <div className="app-brand app-brand--login">
          <span className="app-brand__mark" aria-hidden="true">GV</span>
          <span>{runtimeConfig.appTitle}</span>
        </div>
        <h1>{newPasswordRequired ? 'Choose a new password' : resetMode === 'request' ? 'Reset password' : resetMode === 'confirm' ? 'Enter reset code' : 'Sign in'}</h1>
        <p className="text-base">
          {newPasswordRequired
            ? 'Choose a permanent password below, or use your Google account instead.'
            : resetMode === 'request'
              ? 'We will send a password-reset code to your verified email address.'
              : resetMode === 'confirm'
                ? 'Enter the emailed code and choose a new password.'
            : 'Search and save active federal contract opportunities.'}
        </p>
        {error && <div className="usa-alert usa-alert--error" role="alert"><div className="usa-alert__body"><p className="usa-alert__text">{error}</p></div></div>}
        {message && <div className="usa-alert usa-alert--info" role="status"><div className="usa-alert__body"><p className="usa-alert__text">{message}</p></div></div>}
        <form className="usa-form" onSubmit={submit}>
          {!newPasswordRequired && resetMode !== 'confirm' && (
            <>
              <label className="usa-label" htmlFor="email">Email</label>
              <input className="usa-input" id="email" type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} />
            </>
          )}
          {resetMode === 'confirm' && (
            <>
              <label className="usa-label" htmlFor="reset-email">Email</label>
              <input className="usa-input" id="reset-email" type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} />
              <label className="usa-label" htmlFor="confirmation-code">Reset code</label>
              <input className="usa-input" id="confirmation-code" inputMode="numeric" autoComplete="one-time-code" required value={confirmationCode} onChange={(event) => setConfirmationCode(event.target.value)} />
            </>
          )}
          {resetMode !== 'request' && (
            <>
              <label className="usa-label" htmlFor="password">{creatingPassword ? 'New password' : 'Password'}</label>
              <input
                className="usa-input"
                id="password"
                type="password"
                autoComplete={creatingPassword ? 'new-password' : 'current-password'}
                minLength={creatingPassword ? 12 : undefined}
                required
                value={password}
                aria-describedby={creatingPassword ? 'login-password-requirements' : undefined}
                aria-invalid={creatingPassword && password.length > 0 && !passwordValid}
                onChange={(event) => setPassword(event.target.value)}
              />
              {creatingPassword && (
                <>
                  <label className="usa-label" htmlFor="confirm-password">Confirm new password</label>
                  <input
                    className="usa-input"
                    id="confirm-password"
                    type="password"
                    autoComplete="new-password"
                    minLength={12}
                    required
                    value={confirmPassword}
                    aria-describedby="login-password-requirements-match"
                    aria-invalid={confirmPassword.length > 0 && !passwordsMatch}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                  />
                  <PasswordRequirements
                    password={password}
                    confirmPassword={confirmPassword}
                    id="login-password-requirements"
                  />
                </>
              )}
            </>
          )}
          <button className="usa-button width-full margin-top-3" type="submit" disabled={submitting || (creatingPassword && (!passwordValid || !passwordsMatch))}>
            {submitting ? 'Please wait…' : newPasswordRequired ? 'Set password' : resetMode === 'request' ? 'Send reset code' : resetMode === 'confirm' ? 'Reset password' : 'Sign in'}
          </button>
        </form>
        {resetMode === 'none' && (
          <>
            <div className="login-divider" aria-hidden="true"><span>or</span></div>
            <button
              className="usa-button usa-button--outline width-full google-signin-button"
              type="button"
              disabled={submitting || googleSubmitting}
              onClick={submitGoogle}
            >
              <span className="google-signin-button__mark" aria-hidden="true">G</span>
              {googleSubmitting ? 'Opening Google…' : newPasswordRequired ? 'Use Google instead' : 'Continue with Google'}
            </button>
            <p className="login-google-note">
              Use the Google account with the same email address as your GovVue Light invitation.
            </p>
          </>
        )}
        {!newPasswordRequired && (
          <button
            className="usa-button usa-button--unstyled margin-top-2"
            type="button"
            onClick={() => {
              setResetMode(resetMode === 'none' ? 'request' : 'none');
              setConfirmationCode('');
              setPassword('');
              setConfirmPassword('');
              setError('');
              setMessage('');
            }}
          >{resetMode === 'none' ? 'Forgot password?' : 'Back to sign in'}</button>
        )}
        <nav className="login-public-links" aria-label="Public information">
          <Link to="/about">About</Link>
          <Link to="/privacy">Privacy</Link>
          <Link to="/terms">Terms</Link>
        </nav>
      </div>
    </main>
  );
}
