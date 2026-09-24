import { Amplify } from 'aws-amplify';
import 'aws-amplify/auth/enable-oauth-listener';
import {
  confirmResetPassword,
  confirmSignIn,
  fetchAuthSession,
  resetPassword,
  signIn,
  signInWithRedirect,
  signOut,
  updatePassword,
  type SignInOutput,
} from 'aws-amplify/auth';
import { Hub } from 'aws-amplify/utils';
import { runtimeConfig } from '../runtimeConfig';

const OAUTH_ERROR_STORAGE_KEY = 'govvue.oauth.error';

export function oauthErrorMessage(error: unknown): string {
  const message = error instanceof Error
    ? error.message
    : typeof error === 'string'
      ? error
      : 'Google sign-in could not be completed. Please try again.';

  if (message.includes('No invited GovVue Light account matches this Google email address')) {
    return 'This Google account is not authorized for GovVue Light. Ask an administrator to invite this exact email address, then try again.';
  }
  if (message.includes('User cancelled OAuth flow')) {
    return 'Google sign-in was canceled. Please try again when you are ready.';
  }
  return message;
}

// Amplify can finish the OAuth callback while React is still starting. Preserve
// an early failure so the login page can show it after the provider mounts.
Hub.listen('auth', ({ payload }) => {
  if (payload.event === 'signInWithRedirect_failure') {
    const data = payload.data as { error?: unknown } | undefined;
    window.sessionStorage.setItem(OAUTH_ERROR_STORAGE_KEY, oauthErrorMessage(data?.error));
  } else if (payload.event === 'signedIn' || payload.event === 'signInWithRedirect') {
    window.sessionStorage.removeItem(OAUTH_ERROR_STORAGE_KEY);
  }
});

Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: runtimeConfig.userPoolId,
      userPoolClientId: runtimeConfig.userPoolClientId,
      loginWith: {
        email: true,
        oauth: {
          domain: runtimeConfig.cognitoDomain.replace(/^https?:\/\//, ''),
          scopes: ['email', 'openid', 'profile'],
          redirectSignIn: [`${window.location.origin}/login`],
          redirectSignOut: [`${window.location.origin}/login`],
          responseType: 'code',
        },
      },
    },
  },
});

export type LoginResult = Pick<SignInOutput, 'isSignedIn' | 'nextStep'>;

export async function login(email: string, password: string): Promise<LoginResult> {
  try {
    return await signIn({ username: email, password });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (message.includes('already a signed in user')) {
      await signOut();
      return signIn({ username: email, password });
    }
    throw error;
  }
}

export async function completeNewPassword(password: string): Promise<LoginResult> {
  return confirmSignIn({ challengeResponse: password });
}

export async function loginWithGoogle(returnTo: string): Promise<void> {
  window.sessionStorage.setItem('govvue.oauth.returnTo', returnTo);
  window.sessionStorage.removeItem(OAUTH_ERROR_STORAGE_KEY);
  await signInWithRedirect({
    provider: 'Google',
    options: { prompt: 'SELECT_ACCOUNT' },
  });
}

export async function logout(): Promise<void> {
  window.sessionStorage.removeItem('govvue.oauth.returnTo');
  await signOut();
}

export async function currentUser(): Promise<{ username: string; email: string; role: 'admin' | 'user'; groups: string[] } | null> {
  try {
    const session = await fetchAuthSession();
    const payload = session.tokens?.idToken?.payload;
    if (!payload) return null;
    const rawGroups = payload['cognito:groups'];
    const groups = Array.isArray(rawGroups)
      ? rawGroups.map(String)
      : typeof rawGroups === 'string'
        ? rawGroups.replace(/^\[|\]$/g, '').split(',').map((value) => value.trim()).filter(Boolean)
        : [];
    const username = String(payload['cognito:username'] ?? payload.sub ?? '');
    return {
      username,
      email: String(payload.email ?? username),
      role: groups.includes('admin') ? 'admin' : 'user',
      groups,
    };
  } catch {
    return null;
  }
}

export function consumeOAuthError(): string {
  const message = window.sessionStorage.getItem(OAUTH_ERROR_STORAGE_KEY) ?? '';
  window.sessionStorage.removeItem(OAUTH_ERROR_STORAGE_KEY);
  return message;
}

export async function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  await updatePassword({ oldPassword, newPassword });
}

export async function beginPasswordReset(username: string) {
  return resetPassword({ username });
}

export async function finishPasswordReset(
  username: string,
  confirmationCode: string,
  newPassword: string,
): Promise<void> {
  await confirmResetPassword({ username, confirmationCode, newPassword });
}

export async function idToken(): Promise<string | null> {
  try {
    const session = await fetchAuthSession();
    return session.tokens?.idToken?.toString() ?? null;
  } catch {
    return null;
  }
}
