# Hostinger Draft Importer — Fixed Version

This version fixes Hostinger/Dovecot Drafts-folder namespaces such as:

- INBOX.Drafts
- INBOX/Drafts
- Drafts

## Run on macOS

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Run on Windows

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Test the connection first. The app should display the exact Drafts folder detected on the server.
