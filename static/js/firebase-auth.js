/**
 * Firebase Google sign-in → Flask session via /auth/session
 */
import { initializeApp } from 'https://www.gstatic.com/firebasejs/11.6.0/firebase-app.js';
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut,
} from 'https://www.gstatic.com/firebasejs/11.6.0/firebase-auth.js';

const params = new URLSearchParams(window.location.search);
const nextPath = params.get('next') || '/';

function showError(msg) {
  const el = document.getElementById('loginError');
  if (!el) return;
  el.textContent = msg;
  el.classList.remove('hidden');
}

async function loadConfig() {
  const res = await fetch('/auth/config', { credentials: 'same-origin' });
  if (!res.ok) throw new Error('Could not load auth config');
  return res.json();
}

async function establishSession(idToken) {
  const res = await fetch('/auth/session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ idToken }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const code = data.error || 'login_failed';
    if (code === 'not_allowed') {
      throw new Error('This Google account is not on the family allow list.');
    }
    throw new Error('Sign-in failed. Please try again.');
  }
  if (data.displayName) {
    try {
      localStorage.setItem('username', data.displayName);
    } catch (e) {
      /* ignore */
    }
  }
  window.location.href = nextPath;
}

async function init() {
  const cfg = await loadConfig();
  if (cfg.mode !== 'firebase') return;

  const app = initializeApp({
    apiKey: cfg.apiKey,
    authDomain: cfg.authDomain,
    projectId: cfg.projectId,
    appId: cfg.appId,
  });
  const auth = getAuth(app);
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: 'select_account' });

  const btn = document.getElementById('googleSignInBtn');
  if (!btn) return;

  btn.addEventListener('click', async () => {
    btn.disabled = true;
    try {
      const cred = await signInWithPopup(auth, provider);
      const idToken = await cred.user.getIdToken(true);
      await establishSession(idToken);
    } catch (err) {
      console.error(err);
      showError(err.message || 'Sign-in cancelled or failed.');
      try {
        await signOut(auth);
      } catch (e) {
        /* ignore */
      }
    } finally {
      btn.disabled = false;
    }
  });
}

init().catch((err) => {
  console.error(err);
  showError('Could not start sign-in. Check server configuration.');
});
