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
