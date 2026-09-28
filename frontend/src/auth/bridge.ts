import { runtimeConfig } from '../runtimeConfig';

export interface BridgeUser {
  username: string;
  email: string;
  role: 'admin' | 'user';
  groups: string[];
}

export interface BridgeSession {
  user: BridgeUser | null;
  token: string | null;
}

interface BridgeReply extends BridgeSession {
  kind: 'govvue-auth-reply';
  requestId: string;
}

const peerOrigin = window.location.origin === runtimeConfig.adminBaseUrl
  ? runtimeConfig.appBaseUrl
  : runtimeConfig.adminBaseUrl;

let frameReady: Promise<HTMLIFrameElement> | null = null;

function peerFrame(): Promise<HTMLIFrameElement> {
  if (frameReady) return frameReady;
  let frame: HTMLIFrameElement;
  frameReady = new Promise<HTMLIFrameElement>((resolve, reject) => {
    frame = document.createElement('iframe');
    frame.title = 'GovVue Light shared sign-in';
    frame.setAttribute('aria-hidden', 'true');
    frame.style.display = 'none';
    frame.src = `${peerOrigin}/auth-bridge`;
    const timer = window.setTimeout(() => {
      window.removeEventListener('message', ready);
      reject(new Error('Sign-in bridge did not load'));
    }, 8000);
    function ready(event: MessageEvent) {
      if (event.origin !== peerOrigin || event.source !== frame.contentWindow) return;
      if (event.data?.kind !== 'govvue-auth-ready') return;
      window.clearTimeout(timer);
      window.removeEventListener('message', ready);
      resolve(frame);
    }
    frame.onerror = () => {
      window.clearTimeout(timer);
      window.removeEventListener('message', ready);
      reject(new Error('Sign-in bridge is unavailable'));
    };
    window.addEventListener('message', ready);
    document.body.append(frame);
  }).catch((error) => {
    frame.remove();
    frameReady = null;
    throw error;
  });
  return frameReady!;
}

async function requestPeer(action: 'session' | 'logout'): Promise<BridgeSession | null> {
  if (window.parent !== window || window.location.pathname === '/auth-bridge') return null;
  try {
    const frame = await peerFrame();
    const requestId = crypto.randomUUID();
    return await new Promise<BridgeSession | null>((resolve) => {
      const timer = window.setTimeout(() => {
        window.removeEventListener('message', receive);
        resolve(null);
      }, 8000);
      function receive(event: MessageEvent) {
        if (event.origin !== peerOrigin || event.source !== frame.contentWindow) return;
        const value = event.data as Partial<BridgeReply> | null;
        if (value?.kind !== 'govvue-auth-reply' || value.requestId !== requestId) return;
        window.clearTimeout(timer);
        window.removeEventListener('message', receive);
        resolve({ user: value.user ?? null, token: value.token ?? null });
      }
      window.addEventListener('message', receive);
      frame.contentWindow?.postMessage({ kind: 'govvue-auth-request', action, requestId }, peerOrigin);
    });
  } catch {
    return null;
  }
}

export function peerSession(): Promise<BridgeSession | null> {
  return requestPeer('session');
}

export function peerLogout(): Promise<void> {
  return requestPeer('logout').then(() => undefined);
}
