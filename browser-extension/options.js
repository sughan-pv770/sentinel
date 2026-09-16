// options.js — SentinelX Extension Options Page

async function load() {
  const data = await chrome.storage.sync.get('settings');
  const s = data.settings || {};

  document.getElementById('gateway-url').value   = s.gatewayUrl || 'http://localhost:8080';
  document.getElementById('enabled').checked      = s.enabled !== false;
  document.getElementById('notify-revoke').checked  = s.notifyOnRevoke !== false;
  document.getElementById('notify-restrict').checked = s.notifyOnRestrict !== false;
  document.getElementById('notify-stepup').checked  = s.notifyOnStepUp !== false;
}

document.getElementById('save-btn').addEventListener('click', () => {
  const settings = {
    gatewayUrl:       document.getElementById('gateway-url').value.trim().replace(/\/$/, ''),
    enabled:          document.getElementById('enabled').checked,
    notifyOnRevoke:   document.getElementById('notify-revoke').checked,
    notifyOnRestrict: document.getElementById('notify-restrict').checked,
    notifyOnStepUp:   document.getElementById('notify-stepup').checked,
  };

  chrome.runtime.sendMessage({ type: 'SAVE_SETTINGS', settings }, () => {
    const msg = document.getElementById('saved-msg');
    msg.classList.add('show');
    setTimeout(() => msg.classList.remove('show'), 2500);
  });
});

document.getElementById('test-connection').addEventListener('click', async () => {
  const url = document.getElementById('gateway-url').value.trim().replace(/\/$/, '');
  const result = document.getElementById('ping-result');
  result.textContent = 'Testing…';
  result.className = 'ping-result';

  chrome.runtime.sendMessage({ type: 'PING_GATEWAY' }, (res) => {
    if (res?.ok) {
      result.textContent = `✓ Connected — gateway is reachable at ${url}`;
      result.className = 'ping-result ping-ok';
    } else {
      result.textContent = `✗ Cannot reach gateway at ${url}. Is it running?`;
      result.className = 'ping-result ping-fail';
    }
  });
});

load().catch(console.error);
