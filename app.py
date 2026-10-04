import imaplib
import re
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import pandas as pd
import streamlit as st


IMAP_HOST = "imap.hostinger.com"
IMAP_PORT = 993

REQUIRED_COLUMNS = ["To", "Subject", "Body"]
OPTIONAL_COLUMNS = ["CC", "BCC", "First Name", "Company", "Attachment"]


def clean_cell(value):
    """Turn empty/NaN Excel cells into empty strings."""
    if pd.isna(value):
        return ""
    return str(value).strip()


def valid_email_list(value):
    """
    Basic validation for one or more addresses separated by comma or semicolon.
    This is intentionally lightweight; the mail server remains the final authority.
    """
    value = clean_cell(value)
    if not value:
        return True

    addresses = [x.strip() for x in re.split(r"[;,]", value) if x.strip()]
    pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    return all(pattern.match(address) for address in addresses)


def connect_to_hostinger(email_address, password):
    client = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    client.login(email_address, password)
    return client


def decode_mailbox_name(raw_name):
    """
    Extract a mailbox name from a typical IMAP LIST response.
    Examples may look like:
    (\\HasNoChildren \\Drafts) "/" "Drafts"
    """
    text = raw_name.decode("utf-8", errors="replace")

    # Last quoted item is usually the mailbox name.
    quoted = re.findall(r'"([^"]*)"', text)
    if quoted:
        return quoted[-1]

    # Fallback: take the last whitespace-delimited token.
    return text.split()[-1].strip('"')


def find_drafts_folder(client):
    status, folders = client.list()
    if status != "OK" or not folders:
        raise RuntimeError("Could not list mailbox folders.")

    candidates = []

    for raw in folders:
        text = raw.decode("utf-8", errors="replace")
        folder_name = decode_mailbox_name(raw)

        if "\\Drafts" in text:
            return folder_name

        if folder_name.lower() in {
            "drafts",
            "draft",
            "inbox.drafts",
            "inbox/drafts",
        }:
            candidates.append(folder_name)

    if candidates:
        return candidates[0]

    # Common fallback. We verify it exists.
    status, _ = client.select("Drafts", readonly=True)
    if status == "OK":
        client.close()
        return "Drafts"

    raise RuntimeError(
        "I connected successfully, but I could not identify the Drafts folder."
    )


def personalize(text, first_name="", company=""):
    text = clean_cell(text)
    replacements = {
        "{{First Name}}": clean_cell(first_name),
        "{{FirstName}}": clean_cell(first_name),
        "{{Company}}": clean_cell(company),
    }
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text


def create_message(sender, row):
    to_value = clean_cell(row.get("To", ""))
    cc_value = clean_cell(row.get("CC", ""))
    bcc_value = clean_cell(row.get("BCC", ""))
    first_name = clean_cell(row.get("First Name", ""))
    company = clean_cell(row.get("Company", ""))

    subject = personalize(row.get("Subject", ""), first_name, company)
    body = personalize(row.get("Body", ""), first_name, company)

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_value
    if cc_value:
        msg["Cc"] = cc_value
    if bcc_value:
        # Keeping Bcc in a draft is useful for review before sending.
        msg["Bcc"] = bcc_value

    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()

    msg.set_content(body)
    return msg


def append_draft(client, drafts_folder, message):
    flags = r"(\Draft)"
    when = imaplib.Time2Internaldate(datetime.now().astimezone())
    status, response = client.append(
        drafts_folder,
        flags,
        when,
        message.as_bytes(),
    )
    if status != "OK":
        raise RuntimeError(f"Server rejected the draft: {response}")


def validate_dataframe(df):
    problems = []

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        problems.append("Missing required columns: " + ", ".join(missing))
        return problems

    for idx, row in df.iterrows():
        excel_row = idx + 2

        to_value = clean_cell(row.get("To", ""))
        subject = clean_cell(row.get("Subject", ""))
        body = clean_cell(row.get("Body", ""))

        if not to_value:
            problems.append(f"Row {excel_row}: To is empty.")
        elif not valid_email_list(to_value):
            problems.append(f"Row {excel_row}: To contains an invalid email address.")

        if clean_cell(row.get("CC", "")) and not valid_email_list(row.get("CC", "")):
            problems.append(f"Row {excel_row}: CC contains an invalid email address.")

        if clean_cell(row.get("BCC", "")) and not valid_email_list(row.get("BCC", "")):
            problems.append(f"Row {excel_row}: BCC contains an invalid email address.")

        if not subject:
            problems.append(f"Row {excel_row}: Subject is empty.")

        if not body:
            problems.append(f"Row {excel_row}: Body is empty.")

    return problems


st.set_page_config(
    page_title="Hostinger Draft Importer",
    page_icon="📧",
    layout="wide",
)

st.title("📧 Hostinger Email Draft Importer")
st.caption(
    "Upload your Excel file and create messages in your Hostinger Drafts folder. "
    "This app does not send email."
)

with st.sidebar:
    st.header("Hostinger mailbox")

    mailbox = st.text_input(
        "Email address",
        placeholder="you@yourdomain.com",
    )

    password = st.text_input(
        "Mailbox password",
        type="password",
        help="The password is used only for this running session and is not written to a file.",
    )

    st.info(
        "IMAP server: imap.hostinger.com\n\n"
        "Port: 993\n\n"
        "Security: SSL"
    )

uploaded_file = st.file_uploader(
    "Upload the Excel template",
    type=["xlsx"],
)

df = None

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file, dtype=object)
        df = df.dropna(how="all").reset_index(drop=True)

        st.subheader("1. Preview")
        st.write(f"Rows detected: **{len(df)}**")
        st.dataframe(df, use_container_width=True, hide_index=True)

        problems = validate_dataframe(df)

        if problems:
            st.error(
                "Please fix these Excel issues before importing:\n\n"
                + "\n".join(f"- {item}" for item in problems[:30])
            )
            if len(problems) > 30:
                st.warning(f"There are {len(problems) - 30} more validation issues.")
        else:
            st.success("Excel file looks ready.")

    except Exception as exc:
        st.error(f"Could not read the Excel file: {exc}")

st.divider()
st.subheader("2. Test mailbox connection")

if st.button("Test Hostinger Connection", type="secondary"):
    if not mailbox or not password:
        st.error("Enter your Hostinger email address and mailbox password first.")
    else:
        client = None
        try:
            client = connect_to_hostinger(mailbox, password)
            drafts_folder = find_drafts_folder(client)
            st.success(
                f"Connection successful. Drafts folder detected as: {drafts_folder}"
            )
        except Exception as exc:
            st.error(f"Connection failed: {exc}")
        finally:
            if client is not None:
                try:
                    client.logout()
                except Exception:
                    pass

st.divider()
st.subheader("3. Create drafts")

confirmation = st.checkbox(
    "I understand this will add draft messages to my Hostinger mailbox."
)

create_clicked = st.button(
    "Create Drafts",
    type="primary",
    disabled=not confirmation,
)

if create_clicked:
    if not mailbox or not password:
        st.error("Enter your Hostinger email address and mailbox password.")
    elif df is None:
        st.error("Upload an Excel file first.")
    else:
        problems = validate_dataframe(df)

        if problems:
            st.error("Fix the Excel validation errors before importing.")
        else:
            client = None
            results = []
            progress = st.progress(0)
            status_box = st.empty()

            try:
                client = connect_to_hostinger(mailbox, password)
                drafts_folder = find_drafts_folder(client)

                total = len(df)

                for idx, row in df.iterrows():
                    excel_row = idx + 2
                    recipient = clean_cell(row.get("To", ""))

                    status_box.write(
                        f"Creating draft {idx + 1} of {total}: {recipient}"
                    )

                    try:
                        message = create_message(mailbox, row)
                        append_draft(client, drafts_folder, message)

                        results.append(
                            {
                                "Excel Row": excel_row,
                                "To": recipient,
                                "Subject": clean_cell(row.get("Subject", "")),
                                "Status": "Created",
                                "Error": "",
                            }
                        )

                    except Exception as row_exc:
                        results.append(
                            {
                                "Excel Row": excel_row,
                                "To": recipient,
                                "Subject": clean_cell(row.get("Subject", "")),
                                "Status": "Failed",
                                "Error": str(row_exc),
                            }
                        )

                    progress.progress((idx + 1) / total)

                result_df = pd.DataFrame(results)
                created = int((result_df["Status"] == "Created").sum())
                failed = int((result_df["Status"] == "Failed").sum())

                status_box.empty()

                if failed == 0:
                    st.success(
                        f"Finished. {created} draft(s) were created successfully."
                    )
                else:
                    st.warning(
                        f"Finished. {created} draft(s) created, {failed} failed."
                    )

                st.dataframe(
                    result_df,
                    use_container_width=True,
                    hide_index=True,
                )

                st.download_button(
                    "Download Import Results",
                    data=result_df.to_csv(index=False).encode("utf-8"),
                    file_name="hostinger_draft_import_results.csv",
                    mime="text/csv",
                )

            except Exception as exc:
                st.error(f"Import stopped: {exc}")

            finally:
                if client is not None:
                    try:
                        client.logout()
                    except Exception:
                        pass

st.divider()
st.caption(
    "Tip: Test with 1–2 rows first. After you confirm the drafts appear correctly "
    "in Hostinger Webmail, import the larger sheet."
)
