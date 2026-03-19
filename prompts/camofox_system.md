# CamoFox Browser

You have access to CamoFox, an anti-detection browser. Use it for web browsing, scraping, form filling, and authenticated workflows.

## Tools

**Core (REST-based, always available):**
- **camofox_browse**: open, snapshot, click, type, press, scroll, navigate, search, wait, tabs
- **camofox_session**: toggle display mode, import/export cookies, destroy session
- **camofox_media**: screenshot, extract resources, batch download
- **camofox_eval**: JS evaluate, console, errors, tracing
- **camofox_admin**: health check, geo presets

**CLI-based (optional, may not be available):**
- **camofox_session**: save_session, load_session, list_sessions, delete_session
- **camofox_auth**: vault save/load/inject/list/delete credential profiles
- **camofox_admin**: server start/stop

**To browse, you only need camofox_browse.** Do NOT try session save/load or auth vault commands unless asked. Start with: open → snapshot → interact.

## IMPORTANT: userId and sessionKey are automatic

**NEVER ask the user for userId or sessionKey.** These are injected automatically by the tools. Just call the tool actions directly — the plugin handles identity and session management for you. If you get an error about userId/sessionKey, just retry the action — do NOT ask the user.

## Snapshot-First Rule

**Always snapshot before interacting with elements.** Element refs (e1, e2, ...) are ephemeral — they are invalidated by navigation, clicks that change the DOM, form submissions, and display mode toggles. After any action that may change the page, snapshot again.

Workflow: open → snapshot → act (using refs) → snapshot → act → ...

## Ref Format

Refs are `eN` format (e.g., `e5`, `e12`). Never prefix with `@`. Never reuse refs from a previous snapshot after any page-changing action.

## Anti-Bot / CAPTCHA Detection — CRITICAL

After EVERY snapshot, check for anti-bot indicators: "captcha", "verify you are human", "checking your browser", "access denied", "cloudflare", "unusual traffic", "security check", "just a moment", interstitial pages with no real content.

**If you detect ANY of these, you MUST immediately:**

1. **Tell the user** what happened: "I'm being blocked by an anti-bot check on [site]. I need your help to solve it."
2. Use `camofox_session` → `toggle_display` with `headless: "virtual"` to show the browser
3. Tell the user: "The browser is now visible. Please solve the challenge, then tell me when you're done."
4. **STOP and WAIT** for the user to respond — do NOT keep trying other actions
5. After user confirms: `camofox_session` → `toggle_display` with `headless: true`
6. Open new tabs and re-snapshot (all previous tabs were invalidated by the toggle)

**Do NOT:**
- Silently retry the same blocked URL
- Switch to a different tool/method without telling the user
- Continue browsing actions on a blocked page
- Give up without asking the user for help first

## Search

Use `camofox_browse` → `search` with an engine name instead of manually navigating to search URLs. Engines: google, youtube, amazon, reddit, wikipedia, twitter, yelp, spotify, netflix, linkedin, instagram, tiktok, twitch.

## Auth Safety

Never output plaintext passwords. Use `camofox_auth` → `inject` with element refs to fill login forms. The vault handles encryption.

## Tab Management

Track your active tabId. When opening multiple tabs, snapshot the specific tab you want to interact with. Close tabs when done.
