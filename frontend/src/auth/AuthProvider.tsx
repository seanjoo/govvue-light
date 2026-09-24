import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  completeNewPassword,
  currentUser,
  login,
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

  const signOutUser = useCallback(async () => {
    await logout();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, signIn: signInUser, setNewPassword, signOut: signOutUser }),
    [user, loading, signInUser, setNewPassword, signOutUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
