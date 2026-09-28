import { useEffect } from 'react';
import { localCurrentUser, localIdToken, localLogout } from './cognito';
import { runtimeConfig } from '../runtimeConfig';

export default function AuthBridgePage() {
  useEffect(() => {
    const allowedOrigin = window.location.origin === runtimeConfig.adminBaseUrl
      ? runtimeConfig.appBaseUrl
      : runtimeConfig.adminBaseUrl;
    async function receive(event: MessageEvent) {
      if (event.origin !== allowedOrigin || event.source !== window.parent) return;
      const value = event.data as { kind?: string; action?: string; requestId?: string } | null;
      if (value?.kind !== 'govvue-auth-request' || !value.requestId) return;
      if (value.action === 'logout') await localLogout().catch(() => undefined);
      if (value.action !== 'session' && value.action !== 'logout') return;
      const user = value.action === 'session' ? await localCurrentUser() : null;
      const token = user ? await localIdToken() : null;
      window.parent.postMessage({ kind: 'govvue-auth-reply', requestId: value.requestId, user, token }, allowedOrigin);
    }
    window.addEventListener('message', receive);
    window.parent.postMessage({ kind: 'govvue-auth-ready' }, allowedOrigin);
    return () => window.removeEventListener('message', receive);
  }, []);
  return null;
}
