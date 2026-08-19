const form = document.getElementById('login-form');
const button = document.getElementById('btn');
const buttonLabel = button.querySelector('.button-label');
const input = document.getElementById('pw');
const error = document.getElementById('login-error');

let submitting = false;

try {
  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
  sessionStorage.removeItem('cardiollm_force_login_top');
} catch (_error) {
  // Storage may be unavailable in hardened browser modes.
}

window.scrollTo(0, 0);
document.documentElement.scrollTop = 0;
document.body.scrollTop = 0;

function setError(message) {
  error.textContent = message;
  input.setAttribute('aria-invalid', message ? 'true' : 'false');
}

function setSubmitting(active) {
  submitting = active;
  button.disabled = active;
  form.setAttribute('aria-busy', active ? 'true' : 'false');
  buttonLabel.textContent = active ? '驗證中' : '驗證並進入';
}

async function doLogin(event) {
  event.preventDefault();
  if (submitting) return;

  const password = input.value;
  if (!password) {
    setError('請輸入存取密碼');
    input.focus();
    return;
  }

  setError('');
  setSubmitting(true);

  try {
    const response = await fetch('/login', {
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ password }),
    });

    if (response.ok) {
      window.location.replace('/');
      return;
    }

    input.value = '';
    input.focus();
    if (response.status === 429) {
      const retryAfter = Number.parseInt(response.headers.get('Retry-After') || '0', 10);
      const minutes = retryAfter > 0 ? Math.max(1, Math.ceil(retryAfter / 60)) : null;
      setError(minutes ? `嘗試次數過多，請在 ${minutes} 分鐘後重試` : '嘗試次數過多，請稍後再試');
    } else if (response.status === 401 || response.status === 422) {
      setError('密碼不正確');
    } else {
      setError('登入服務暫時無法使用，請稍後再試');
    }
  } catch (_error) {
    setError('無法連線至登入服務，請檢查網路後重試');
  } finally {
    setSubmitting(false);
  }
}

form.addEventListener('submit', doLogin);
input.addEventListener('input', () => {
  if (error.textContent) setError('');
});
