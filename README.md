# Hostinger Draft Importer — Cloudflare + Python Backend

This repository uses a hybrid architecture because Hostinger IMAP works reliably from a normal Python server, while Cloudflare Workers may reject the direct TCP destination.

# Hostinger Draft Importer

A small local Streamlit app that imports email rows from an Excel file into
the Drafts folder of a Hostinger Email mailbox.

## What it does

- Reads `.xlsx` files
- Requires `To`, `Subject`, and `Body`
- Supports optional `CC`, `BCC`, `First Name`, and `Company`
- Supports placeholders:
  - `{{First Name}}`
  - `{{FirstName}}`
  - `{{Company}}`
- Tests the Hostinger IMAP connection
- Creates drafts using IMAP APPEND
- Does NOT send email
- Produces a downloadable import-results CSV

## Hostinger connection used

- Host: `imap.hostinger.com`
- Port: `993`
- SSL: Yes

## Windows setup

1. Install Python 3.
2. Open Command Prompt in this project folder.
3. Run:

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## macOS setup

Open Terminal in this project folder:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Streamlit should open your browser automatically. If it does not, visit:

`http://localhost:8501`

## Recommended first test

Use only 1 or 2 rows in your Excel file first.

After clicking Create Drafts:

1. Open Hostinger Webmail.
2. Open the Drafts folder.
3. Verify recipient, subject, and body.
4. Then use your full spreadsheet.

## Security

The app asks for your mailbox password at runtime. Do not hard-code the
password into `app.py`.


## Architecture

```text
Browser
  |
  v
Cloudflare Worker + Static Frontend
  |
  | HTTPS /api/*
  v
Render / Railway FastAPI Backend
  |
  | IMAP SSL :993
  v
Hostinger Email
```

The mailbox password is **not stored in GitHub**. It is sent at runtime over HTTPS to your Cloudflare Worker, which securely proxies the request to your backend. The backend uses it only for that request.

A shared `BACKEND_SECRET` prevents people from calling the backend API directly.

---

# Repository structure

```text
.
├── package.json
├── wrangler.jsonc
├── render.yaml
├── src/
│   └── index.js
├── public/
│   ├── index.html
│   ├── styles.css
│   └── app.js
└── backend/
    ├── main.py
    └── requirements.txt
```

---

# STEP 1 — Push this repository to GitHub

Replace the old Streamlit files with this project, then:

```bash
git add .
git commit -m "Use Cloudflare frontend with Python IMAP backend"
git push
```

You no longer need the old root-level:

- `app.py`
- `requirements.txt`
- Streamlit configuration

---

# STEP 2 — Deploy the backend to Render

## Option A — Render Blueprint

Because this repo contains `render.yaml`, you can create a new Render Blueprint from the GitHub repo.

When Render asks for `BACKEND_SECRET`, create a long random value, for example:

```text
change-this-to-a-long-random-secret
```

Use a much stronger secret in production.

Render will use:

- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Health endpoint: `/health`

After deployment, Render gives you a URL similar to:

```text
https://hostinger-draft-importer-backend.onrender.com
```

Open:

```text
https://YOUR-RENDER-URL/health
```

You should see:

```json
{
  "ok": true,
  "service": "hostinger-draft-importer-backend"
}
```

## Option B — Manual Render Web Service

Create a new Web Service from the same GitHub repo and use:

Root Directory:
```text
backend
```

Build Command:
```bash
pip install -r requirements.txt
```

Start Command:
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Environment variable:

```text
BACKEND_SECRET=YOUR_LONG_RANDOM_SECRET
```

---

# STEP 3 — Deploy the frontend to Cloudflare

Connect the same GitHub repository to Cloudflare Workers Builds.

Use:

Build command:
```bash
npm install
```

Deploy command:
```bash
npx wrangler deploy
```

Do **not** use `pip install -r requirements.txt` on Cloudflare.

---

# STEP 4 — Add Cloudflare environment variables

In your Cloudflare Worker settings, add:

## Variable

```text
BACKEND_URL
```

Value:

```text
https://YOUR-RENDER-BACKEND.onrender.com
```

Do not add a trailing slash.

## Secret

```text
BACKEND_SECRET
```

Value:

Use the **exact same secret** you configured on Render.

For CLI users:

```bash
npx wrangler secret put BACKEND_SECRET
```

`BACKEND_URL` can be configured in the Cloudflare dashboard or in environment settings.

Do not commit the real secret into `wrangler.jsonc`.

---

# STEP 5 — Redeploy Cloudflare

After adding the variables/secrets, redeploy.

Open your Cloudflare URL.

Click:

```text
Test Hostinger Connection
```

If everything is configured correctly, you should see:

```text
Connected. Drafts folder: INBOX.Drafts
```

(or whatever your Hostinger server calls the Drafts folder).

---

# STEP 6 — Test one draft

Create an Excel file with only one row first.

Required columns:

```text
To
Subject
Body
```

Optional columns:

```text
CC
BCC
First Name
Company
```

Personalization supported:

```text
{{First Name}}
{{FirstName}}
{{Company}}
```

The Qolvia signature is added automatically when the checkbox is enabled.

---

# Security notes

- Never put your Hostinger mailbox password in GitHub.
- Never put `BACKEND_SECRET` in GitHub.
- Use the same `BACKEND_SECRET` on Cloudflare and Render.
- The backend requires the secret on every `/api/*` request.
- The frontend cannot see `BACKEND_SECRET`; only the Cloudflare Worker can.
- Drafts are created through IMAP. This project contains no SMTP sending code.

---

# Railway instead of Render

You can also deploy the `backend` directory to Railway.

Use:

Build:
```bash
pip install -r requirements.txt
```

Start:
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Add:

```text
BACKEND_SECRET=YOUR_LONG_RANDOM_SECRET
```

Then use the Railway HTTPS URL as Cloudflare `BACKEND_URL`.

## About Developer

Developed by: Zeeshan Ahmed Jarral
License: GPLv2 or later
