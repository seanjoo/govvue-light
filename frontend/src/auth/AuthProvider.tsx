import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Hub } from 'aws-amplify/utils';
import {
  completeNewPassword,
  currentUser,
  login,
  loginWithGoogle,
  logout,
  type LoginResult,
} from './cognito';

interface User {
  username: string;
  email: string;
  role: 'admin' | 'user';
  groups: string[];
}

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<LoginResult>;
  setNewPassword: (password: string) => Promise<LoginResult>;
  signInWithGoogle: (returnTo: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setUser(await currentUser());
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  useEffect(() => Hub.listen('auth', ({ payload }) => {
    if (payload.event === 'signedIn' || payload.event === 'tokenRefresh') {
      refresh().finally(() => setLoading(false));
    } else if (payload.event === 'signedOut') {
      setUser(null);
    }
  }), [refresh]);

  const signInUser = useCallback(async (email: string, password: string) => {
    const result = await login(email, password);
    if (result.isSignedIn) await refresh();
    return result;
  }, [refresh]);

  const setNewPassword = useCallback(async (password: string) => {
    const result = await completeNewPassword(password);
    if (result.isSignedIn) await refresh();
    return result;
  }, [refresh]);

  const signInGoogle = useCallback(async (returnTo: string) => {
    setLoading(true);
    try {
      await loginWithGoogle(returnTo);
    } catch (error) {
      setLoading(false);
      throw error;
    }
  }, []);

  const signOutUser = useCallback(async () => {
    await logout();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, signIn: signInUser, setNewPassword, signInWithGoogle: signInGoogle, signOut: signOutUser }),
    [user, loading, signInUser, setNewPassword, signInGoogle, signOutUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
