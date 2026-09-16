# SentinelX Browser Extension

A Chrome/Edge MV3 extension that works as a **universal security overlay** for any web portal.

## What it does

Install it once — it silently watches every portal you log into. When SentinelX gateway is running, it:

| Event | Extension does |
|---|---|
| You log in to any portal | Connects to gateway via SSE, shows 🛡 badge |
| Gateway detects anomaly → **restrict** | Toast banner on the page + browser notification |
| Gateway detects attack → **revoke** | Full-page warning banner + browser notification |
| Gateway triggers **step_up** | Nudge banner → complete MFA in the portal |

## Install (Chrome / Edge)

1. Open `chrome://extensions`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked**
4. Select this `browser-extension/` folder
5. The SentinelX shield appears in your toolbar

## Configuration

Click the extension → **⚙ Settings**:
- Set your **Gateway URL** (default: `http://localhost:8080`)
- Toggle notification preferences

## How portals integrate with it

Any portal that uses SentinelX just needs one line in its root component:

```js
window.__sentinelxPortal = true;  // tells the extension this page is SentinelX-protected
```

The extension auto-detects this flag and activates monitoring immediately.

## Files

| File | Purpose |
|---|---|
| `manifest.json` | Chrome MV3 configuration |
| `background.js` | Service worker — SSE relay, notifications, session tracking |
| `content.js` | Injected into every page — shield badge, in-page banners |
| `popup.html/js` | Toolbar popup — shows active session + risk score |
| `options.html/js` | Settings page — gateway URL, notification toggles |

## Works with any portal

The extension doesn't require any portal modifications. It works by:
1. Watching `fetch()` calls to detect login/logout
2. Connecting to the SentinelX gateway SSE stream once an identity is detected
3. Forwarding security events to the content script via Chrome message passing
