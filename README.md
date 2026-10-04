# Hostinger Draft Importer — Cloudflare Worker Version

This is the Cloudflare-native replacement for the previous Streamlit/Python app.

## Architecture

- `public/` — static frontend (HTML/CSS/JS)
- `src/index.js` — Cloudflare Worker API
- Excel is parsed in the browser with SheetJS
- The Worker connects to Hostinger IMAP over TLS on port 993
- Drafts are created using IMAP APPEND
- No SMTP is used, so the app does not send messages

## Local setup

```bash
npm install
npm run dev
```

Then open the local URL shown by Wrangler.

## Deploy

```bash
npm install
npm run deploy
```

Or connect the GitHub repository to Cloudflare Workers Builds.

### Cloudflare build settings

Build command:
```bash
npm install
```

Deploy command:
```bash
npx wrangler deploy
```

You do not need Python or `requirements.txt` anymore.

## Important

Do not commit real mailbox credentials. The app asks for the email and password at runtime and sends them only to the Worker endpoint over HTTPS for that request.

Test with 1–2 drafts before importing a larger sheet.
