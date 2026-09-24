import { Amplify } from 'aws-amplify';
import 'aws-amplify/auth/enable-oauth-listener';
import {
  confirmResetPassword,
  confirmSignIn,
  fetchAuthSession,
  fetchUserAttributes,
  getCurrentUser,
  resetPassword,
  signIn,
  signInWithRedirect,
  signOut,
  updatePassword,
  type SignInOutput,
} from 'aws-amplify/auth';
import { runtimeConfig } from '../runtimeConfig';

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
  try {
    await signOut();
  } catch {
    // A pending temporary-password challenge has no authenticated session.
  }
  await signInWithRedirect({ provider: 'Google' });
}

export async function logout(): Promise<void> {
  window.sessionStorage.removeItem('govvue.oauth.returnTo');
  await signOut();
}

export async function currentUser(): Promise<{ username: string; email: string; role: 'admin' | 'user'; groups: string[] } | null> {
  try {
    const user = await getCurrentUser();
    const attributes = await fetchUserAttributes();
    const session = await fetchAuthSession();
    const rawGroups = session.tokens?.idToken?.payload['cognito:groups'];
    const groups = Array.isArray(rawGroups)
      ? rawGroups.map(String)
      : typeof rawGroups === 'string'
        ? rawGroups.replace(/^\[|\]$/g, '').split(',').map((value) => value.trim()).filter(Boolean)
        : [];
    return {
      username: user.username,
      email: attributes.email ?? user.username,
      role: groups.includes('admin') ? 'admin' : 'user',
      groups,
    };
  } catch {
    return null;
  }
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
