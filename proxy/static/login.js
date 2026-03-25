const btn = document.getElementById('btn');
const input = document.getElementById('pw');

async function doLogin() {
  btn.textContent = '驗證中...';
  const pw = input.value;

  const r = await fetch('/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password: pw })
  });

  if (r.ok) {
    location.reload();
  } else {
    document.getElementById('err').textContent = '密碼錯誤';
    btn.textContent = '進入系統';
  }
}

btn.onclick = doLogin;
input.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') doLogin();
});