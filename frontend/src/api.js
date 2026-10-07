export const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api';

const KEY = 'pos_auth';

export function getAuth() {
  try {
    return JSON.parse(sessionStorage.getItem(KEY));
  } catch {
    return null;
  }
}
export function saveAuth(auth) {
  sessionStorage.setItem(KEY, JSON.stringify(auth));
}
export function clearAuth() {
  sessionStorage.removeItem(KEY);
}

let refreshing = null;
async function refreshAccess() {
  const auth = getAuth();
  if (!auth?.refresh) return false;
  if (!refreshing) {
    refreshing = fetch(`${API_URL}/auth/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: auth.refresh }),
    })
      .then(async (r) => {
        if (!r.ok) return false;
        const data = await r.json();
        saveAuth({ ...getAuth(), access: data.access });
        return true;
      })
      .catch(() => false)
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

export async function apiFetch(path, options = {}) {
  const send = () => {
    const auth = getAuth();
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    if (auth?.access) headers.Authorization = `Bearer ${auth.access}`;
    return fetch(`${API_URL}${path}`, { ...options, headers });
  };

  let response = await send();
  if (response.status === 401 && (await refreshAccess())) {
    response = await send();
  }
  if (response.status === 401) {
    clearAuth();
    window.dispatchEvent(new Event('auth-expired'));
  }
  return response;
}