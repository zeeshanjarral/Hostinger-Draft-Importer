import imaplib
import os
import re
import secrets
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from html import escape
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


IMAP_HOST = "imap.hostinger.com"
IMAP_PORT = 993

QOLVIA_LOGO_URL = "https://i.ibb.co/DgG0df6q/download.png"

BACKEND_SECRET = os.getenv("BACKEND_SECRET", "").strip()

SIGNATURE_HTML = f"""
<div style="font-family:Arial,Helvetica,sans-serif;color:#111111;margin-top:24px;">
  <div style="margin-bottom:12px;">
    <img src="{QOLVIA_LOGO_URL}"
         alt="Qolvia"
         style="display:block;width:150px;max-width:100%;height:auto;border:0;">
  </div>

  <div style="font-family:Georgia,'Times New Roman',serif;font-size:22px;line-height:1.15;">
    <strong>Samuel F.</strong><br>
    <strong>CTO | Qolvia</strong><br>
    <em style="font-size:20px;">
      We help businesses build, grow, and automate their online presence.
    </em>
  </div>

  <div style="font-family:Georgia,'Times New Roman',serif;font-size:19px;line-height:1.35;margin-top:18px;">
    <a href="mailto:contact@qolvia.io">contact@qolvia.io</a><br>
    <a href="https://qolvia.io">https://qolvia.io</a><br>
    6900 Boulevard Décarie, Montréal, QC, Canada
  </div>
</div>
""".strip()

SIGNATURE_TEXT = """Samuel F.
CTO | Qolvia
We help businesses build, grow, and automate their online presence.

contact@qolvia.io
https://qolvia.io
6900 Boulevard Décarie, Montréal, QC, Canada"""


app = FastAPI(
    title="Hostinger Draft Importer Backend",
    version="1.0.0",
)


class TestRequest(BaseModel):
    email: str
    password: str


class ImportRequest(BaseModel):
    email: str
    password: str
    include_signature: bool = True
    row_offset: int = 0
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=50)


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def verify_secret(x_app_secret: str | None) -> None:
    if not BACKEND_SECRET:
        raise HTTPException(
            status_code=500,
            detail="BACKEND_SECRET is not configured on the backend.",
        )

    if not x_app_secret or not secrets.compare_digest(x_app_secret, BACKEND_SECRET):
        raise HTTPException(status_code=401, detail="Unauthorized.")


def connect_imap(email_address: str, password: str) -> imaplib.IMAP4_SSL:
    client = imaplib.IMAP4_SSL(
        host=IMAP_HOST,
        port=IMAP_PORT,
        timeout=30,
    )
    client.login(email_address, password)
    return client


def decode_mailbox_name(raw_name: bytes) -> str:
    text = raw_name.decode("utf-8", errors="replace").strip()

    match = re.match(r'^\(.*?\)\s+(?:"[^"]*"|NIL)\s+(.+)$', text)
    if match:
        name = match.group(1).strip()
        if name.startswith('"') and name.endswith('"'):
            name = name[1:-1]
        return name

    return text.rsplit(" ", 1)[-1].strip().strip('"')


def mailbox_is_selectable(client: imaplib.IMAP4_SSL, mailbox: str) -> bool:
    try:
        status, _ = client.select(mailbox, readonly=True)
        if status == "OK":
            try:
                client.close()
            except Exception:
                pass
            return True
    except Exception:
        pass

    return False


def find_drafts_folder(client: imaplib.IMAP4_SSL) -> str:
    status, folders = client.list()

    if status != "OK" or not folders:
        raise RuntimeError("Could not list mailbox folders.")

    parsed: list[tuple[str, str]] = []

    for raw in folders:
        if raw is None:
            continue
        text = raw.decode("utf-8", errors="replace")
        name = decode_mailbox_name(raw)
        parsed.append((text, name))

    # Preferred: server explicitly marks the special-use Drafts folder.
    for text, name in parsed:
        if "\\Drafts" in text and mailbox_is_selectable(client, name):
            return name

    likely_names: list[str] = []

    for _, name in parsed:
        lowered = name.lower()

        if lowered in {
            "drafts",
            "draft",
            "inbox.drafts",
            "inbox/drafts",
            "inbox.draft",
            "inbox/draft",
        }:
            likely_names.append(name)
        elif lowered.endswith(".drafts") or lowered.endswith("/drafts"):
            likely_names.append(name)

    for name in likely_names:
        if mailbox_is_selectable(client, name):
            return name

    for fallback in (
        "INBOX.Drafts",
        "INBOX/Drafts",
        "Drafts",
        "INBOX.Draft",
        "INBOX/Draft",
    ):
        if mailbox_is_selectable(client, fallback):
            return fallback

    available = ", ".join(name for _, name in parsed)

    raise RuntimeError(
        "Connected successfully, but the Drafts folder could not be identified. "
        f"Available folders: {available}"
    )


def personalize(text: Any, row: dict[str, Any]) -> str:
    value = clean(text)

    replacements = {
        "{{First Name}}": clean(row.get("First Name")),
        "{{FirstName}}": clean(row.get("First Name")),
        "{{Company}}": clean(row.get("Company")),
    }

    for key, replacement in replacements.items():
        value = value.replace(key, replacement)

    return value


def text_to_html(value: str) -> str:
    return escape(value).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def valid_email_list(value: Any) -> bool:
    value = clean(value)
    if not value:
        return True

    addresses = [x.strip() for x in re.split(r"[;,]", value) if x.strip()]
    pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    return all(pattern.match(address) for address in addresses)


def validate_row(row: dict[str, Any], excel_row: int) -> list[str]:
    issues: list[str] = []

    to_value = clean(row.get("To"))
    subject = clean(row.get("Subject"))
    body = clean(row.get("Body"))

    if not to_value:
        issues.append(f"Row {excel_row}: To is empty.")
    elif not valid_email_list(to_value):
        issues.append(f"Row {excel_row}: To contains an invalid email address.")

    if clean(row.get("CC")) and not valid_email_list(row.get("CC")):
        issues.append(f"Row {excel_row}: CC contains an invalid email address.")

    if clean(row.get("BCC")) and not valid_email_list(row.get("BCC")):
        issues.append(f"Row {excel_row}: BCC contains an invalid email address.")

    if not subject:
        issues.append(f"Row {excel_row}: Subject is empty.")

    if not body:
        issues.append(f"Row {excel_row}: Body is empty.")

    return issues


def create_message(
    sender: str,
    row: dict[str, Any],
    include_signature: bool,
) -> EmailMessage:
    to_value = clean(row.get("To"))
    cc_value = clean(row.get("CC"))
    bcc_value = clean(row.get("BCC"))

    subject = personalize(row.get("Subject"), row)
    body = personalize(row.get("Body"), row)

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_value

    if cc_value:
        msg["Cc"] = cc_value

    if bcc_value:
        # Kept in the draft so the user can review it before sending.
        msg["Bcc"] = bcc_value

    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()

    plain_body = body
    if include_signature:
        plain_body += "\n\n" + SIGNATURE_TEXT

    msg.set_content(plain_body)

    html_body = f"""
    <html>
      <body>
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.6;color:#111111;">
          {text_to_html(body)}
        </div>
        {"<br>" + SIGNATURE_HTML if include_signature else ""}
      </body>
    </html>
    """.strip()

    msg.add_alternative(html_body, subtype="html")

    return msg


def append_draft(
    client: imaplib.IMAP4_SSL,
    drafts_folder: str,
    message: EmailMessage,
) -> None:
    when = imaplib.Time2Internaldate(datetime.now().astimezone())

    status, response = client.append(
        drafts_folder,
        r"(\Draft)",
        when,
        message.as_bytes(),
    )

    if status != "OK":
        raise RuntimeError(f"Hostinger rejected the draft: {response}")


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "hostinger-draft-importer-backend",
    }


@app.post("/api/test")
def test_connection(
    payload: TestRequest,
    x_app_secret: str | None = Header(default=None),
):
    verify_secret(x_app_secret)

    client: imaplib.IMAP4_SSL | None = None

    try:
        client = connect_imap(clean(payload.email), payload.password)
        drafts_folder = find_drafts_folder(client)

        return {
            "ok": True,
            "drafts_folder": drafts_folder,
        }

    except imaplib.IMAP4.error as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Hostinger login/IMAP error: {exc}",
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )

    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass


@app.post("/api/import")
def import_drafts(
    payload: ImportRequest,
    x_app_secret: str | None = Header(default=None),
):
    verify_secret(x_app_secret)

    email_address = clean(payload.email)

    client: imaplib.IMAP4_SSL | None = None
    results: list[dict[str, Any]] = []

    try:
        client = connect_imap(email_address, payload.password)
        drafts_folder = find_drafts_folder(client)

        for index, row in enumerate(payload.rows):
            excel_row = payload.row_offset + index + 2
            recipient = clean(row.get("To"))
            subject = personalize(row.get("Subject"), row)

            issues = validate_row(row, excel_row)

            if issues:
                results.append(
                    {
                        "excel_row": excel_row,
                        "to": recipient,
                        "subject": subject,
                        "status": "Failed",
                        "error": " ".join(issues),
                    }
                )
                continue

            try:
                message = create_message(
                    sender=email_address,
                    row=row,
                    include_signature=payload.include_signature,
                )

                append_draft(
                    client=client,
                    drafts_folder=drafts_folder,
                    message=message,
                )

                results.append(
                    {
                        "excel_row": excel_row,
                        "to": recipient,
                        "subject": subject,
                        "status": "Created",
                        "error": "",
                    }
                )

            except Exception as row_error:
                results.append(
                    {
                        "excel_row": excel_row,
                        "to": recipient,
                        "subject": subject,
                        "status": "Failed",
                        "error": str(row_error),
                    }
                )

        return {
            "ok": True,
            "drafts_folder": drafts_folder,
            "results": results,
        }

    except imaplib.IMAP4.error as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Hostinger login/IMAP error: {exc}",
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )

    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass
