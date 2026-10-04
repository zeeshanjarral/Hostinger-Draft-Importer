import { connect } from "cloudflare:sockets";

const IMAP_HOST = "imap.hostinger.com";
const IMAP_PORT = 993;

const QOLVIA_LOGO_URL = "https://i.ibb.co/DgG0df6q/download.png";

const SIGNATURE_HTML = `
<div style="font-family:Arial,Helvetica,sans-serif;color:#111;margin-top:24px;">
  <div style="margin-bottom:12px;">
    <img src="${QOLVIA_LOGO_URL}"
         alt="Qolvia"
         style="display:block;width:150px;max-width:100%;height:auto;border:0;">
  </div>
  <div style="font-family:Georgia,'Times New Roman',serif;font-size:22px;line-height:1.15;">
    <strong>Samuel F.</strong><br>
    <strong>CTO | Qolvia</strong><br>
    <em style="font-size:20px;">We help businesses build, grow, and automate their online presence.</em>
  </div>
  <div style="font-family:Georgia,'Times New Roman',serif;font-size:19px;line-height:1.35;margin-top:18px;">
    <a href="mailto:contact@qolvia.io">contact@qolvia.io</a><br>
    <a href="https://qolvia.io">https://qolvia.io</a><br>
    6900 Boulevard Décarie, Montréal, QC, Canada
  </div>
</div>`;

const SIGNATURE_TEXT =
`Samuel F.
CTO | Qolvia
We help businesses build, grow, and automate their online presence.

contact@qolvia.io
https://qolvia.io
6900 Boulevard Décarie, Montréal, QC, Canada`;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store"
    }
  });
}

function clean(v) {
  return v == null ? "" : String(v).trim();
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function bodyToHtml(s) {
  return escapeHtml(s).replace(/\r?\n/g, "<br>");
}

function personalize(text, row) {
  return clean(text)
    .replaceAll("{{First Name}}", clean(row["First Name"]))
    .replaceAll("{{FirstName}}", clean(row["First Name"]))
    .replaceAll("{{Company}}", clean(row["Company"]));
}

function base64Utf8(str) {
  const bytes = new TextEncoder().encode(str);
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary);
}

function mimeHeader(value) {
  value = clean(value);
  if (/^[\x20-\x7E]*$/.test(value)) return value;
  return `=?UTF-8?B?${base64Utf8(value)}?=`;
}

function boundary() {
  return "----=_Cloudflare_" + crypto.randomUUID().replaceAll("-", "");
}

function buildMessage(sender, row, includeSignature) {
  const to = clean(row.To);
  const cc = clean(row.CC);
  const bcc = clean(row.BCC);
  const subject = personalize(row.Subject, row);
  const body = personalize(row.Body, row);

  const b = boundary();
  const plain = body + (includeSignature ? "\r\n\r\n" + SIGNATURE_TEXT : "");
  const html = `
<html><body>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.6;color:#111;">
${bodyToHtml(body)}
</div>
${includeSignature ? "<br>" + SIGNATURE_HTML : ""}
</body></html>`.trim();

  const headers = [
    `From: ${sender}`,
    `To: ${to}`,
    cc ? `Cc: ${cc}` : null,
    bcc ? `Bcc: ${bcc}` : null,
    `Subject: ${mimeHeader(subject)}`,
    `Date: ${new Date().toUTCString()}`,
    `Message-ID: <${crypto.randomUUID()}@cloudflare-worker>`,
    `MIME-Version: 1.0`,
    `Content-Type: multipart/alternative; boundary="${b}"`
  ].filter(Boolean);

  return [
    ...headers,
    "",
    `--${b}`,
    `Content-Type: text/plain; charset="UTF-8"`,
    `Content-Transfer-Encoding: 8bit`,
    "",
    plain,
    `--${b}`,
    `Content-Type: text/html; charset="UTF-8"`,
    `Content-Transfer-Encoding: 8bit`,
    "",
    html,
    `--${b}--`,
    ""
  ].join("\r\n");
}

function quoteImap(s) {
  return `"${String(s).replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"`;
}

class ImapClient {
  constructor() {
    this.socket = null;
    this.reader = null;
    this.writer = null;
    this.decoder = new TextDecoder();
    this.encoder = new TextEncoder();
    this.buffer = "";
    this.tag = 0;
  }

  async connect() {
    this.socket = connect(
      { hostname: IMAP_HOST, port: IMAP_PORT },
      { secureTransport: "on" }
    );
    await this.socket.opened;
    this.reader = this.socket.readable.getReader();
    this.writer = this.socket.writable.getWriter();

    const greeting = await this.readUntilLine();
    if (!greeting.startsWith("* OK")) {
      throw new Error("Hostinger IMAP did not return an OK greeting.");
    }
  }

  nextTag() {
    this.tag += 1;
    return "A" + String(this.tag).padStart(4, "0");
  }

  async write(text) {
    await this.writer.write(this.encoder.encode(text));
  }

  async readChunk() {
    const { value, done } = await this.reader.read();
    if (done) throw new Error("IMAP connection closed unexpectedly.");
    this.buffer += this.decoder.decode(value, { stream: true });
  }

  async readUntilLine() {
    while (!this.buffer.includes("\r\n")) {
      await this.readChunk();
    }
    const idx = this.buffer.indexOf("\r\n");
    const line = this.buffer.slice(0, idx);
    this.buffer = this.buffer.slice(idx + 2);
    return line;
  }

  async command(command) {
    const tag = this.nextTag();
    await this.write(`${tag} ${command}\r\n`);

    const lines = [];
    while (true) {
      const line = await this.readUntilLine();
      lines.push(line);
      if (line.startsWith(tag + " ")) {
        if (!line.startsWith(tag + " OK")) {
          throw new Error(line);
        }
        return lines;
      }
    }
  }

  async login(email, password) {
    await this.command(`LOGIN ${quoteImap(email)} ${quoteImap(password)}`);
  }

  async list() {
    return await this.command(`LIST "" "*"`);
  }

  async append(mailbox, rawMessage) {
    const tag = this.nextTag();
    const bytes = this.encoder.encode(rawMessage);

    await this.write(
      `${tag} APPEND ${quoteImap(mailbox)} (\\Draft) {${bytes.byteLength}}\r\n`
    );

    let line = await this.readUntilLine();
    if (!line.startsWith("+")) {
      throw new Error(`IMAP APPEND rejected before upload: ${line}`);
    }

    await this.writer.write(bytes);
    await this.write("\r\n");

    const lines = [line];
    while (true) {
      line = await this.readUntilLine();
      lines.push(line);
      if (line.startsWith(tag + " ")) {
        if (!line.startsWith(tag + " OK")) {
          throw new Error(line);
        }
        return lines;
      }
    }
  }

  async logout() {
    try {
      await this.command("LOGOUT");
    } catch (_) {}
    try { this.writer.releaseLock(); } catch (_) {}
    try { this.reader.releaseLock(); } catch (_) {}
    try { await this.socket.close(); } catch (_) {}
  }
}

function parseMailboxFromListLine(line) {
  // Typical:
  // * LIST (\HasNoChildren \Drafts) "." INBOX.Drafts
  // * LIST (...) "/" "INBOX/Drafts"
  const m = line.match(/^\* LIST \((.*?)\) (?:"([^"]*)"|NIL) (.+)$/i);
  if (!m) return null;
  let name = m[3].trim();
  if (name.startsWith('"') && name.endsWith('"')) {
    name = name.slice(1, -1).replaceAll('\\"', '"').replaceAll("\\\\", "\\");
  }
  return { flags: m[1], delimiter: m[2], name };
}

function detectDraftsFolder(listLines) {
  const folders = listLines
    .filter(x => x.startsWith("* LIST"))
    .map(parseMailboxFromListLine)
    .filter(Boolean);

  const marked = folders.find(f => /\\Drafts/i.test(f.flags));
  if (marked) return marked.name;

  const preferred = [
    "INBOX.Drafts",
    "INBOX/Drafts",
    "Drafts",
    "INBOX.Draft",
    "INBOX/Draft"
  ];

  for (const p of preferred) {
    const found = folders.find(f => f.name.toLowerCase() === p.toLowerCase());
    if (found) return found.name;
  }

  const suffix = folders.find(f => /(^|[./])drafts?$/i.test(f.name));
  if (suffix) return suffix.name;

  throw new Error(
    "Connected, but could not identify the Drafts folder. Available folders: " +
    folders.map(f => f.name).join(", ")
  );
}

function validateRow(row, index) {
  const errors = [];
  const excelRow = index + 2;

  if (!clean(row.To)) errors.push(`Row ${excelRow}: To is empty.`);
  if (!clean(row.Subject)) errors.push(`Row ${excelRow}: Subject is empty.`);
  if (!clean(row.Body)) errors.push(`Row ${excelRow}: Body is empty.`);

  return errors;
}

async function testConnection(email, password) {
  const imap = new ImapClient();
  try {
    await imap.connect();
    await imap.login(email, password);
    const list = await imap.list();
    return detectDraftsFolder(list);
  } finally {
    await imap.logout();
  }
}

async function importDrafts(email, password, rows, includeSignature) {
  const imap = new ImapClient();
  const results = [];

  try {
    await imap.connect();
    await imap.login(email, password);
    const list = await imap.list();
    const draftsFolder = detectDraftsFolder(list);

    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      const validationErrors = validateRow(row, i);

      if (validationErrors.length) {
        results.push({
          row: i + 2,
          to: clean(row.To),
          subject: clean(row.Subject),
          status: "Failed",
          error: validationErrors.join(" ")
        });
        continue;
      }

      try {
        const raw = buildMessage(email, row, includeSignature);
        await imap.append(draftsFolder, raw);

        results.push({
          row: i + 2,
          to: clean(row.To),
          subject: personalize(row.Subject, row),
          status: "Created",
          error: ""
        });
      } catch (err) {
        results.push({
          row: i + 2,
          to: clean(row.To),
          subject: clean(row.Subject),
          status: "Failed",
          error: err?.message || String(err)
        });
      }
    }

    return { draftsFolder, results };
  } finally {
    await imap.logout();
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (!url.pathname.startsWith("/api/")) {
      return env.ASSETS.fetch(request);
    }

    if (request.method !== "POST") {
      return json({ error: "Method not allowed" }, 405);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "Invalid JSON request." }, 400);
    }

    const email = clean(body.email);
    const password = clean(body.password);

    if (!email || !password) {
      return json({ error: "Email and mailbox password are required." }, 400);
    }

    try {
      if (url.pathname === "/api/test") {
        const draftsFolder = await testConnection(email, password);
        return json({
          ok: true,
          draftsFolder
        });
      }

      if (url.pathname === "/api/import") {
        if (!Array.isArray(body.rows) || !body.rows.length) {
          return json({ error: "No Excel rows were provided." }, 400);
        }

        // Simple safety cap for one request.
        if (body.rows.length > 250) {
          return json({
            error: "Please import no more than 250 rows at a time."
          }, 400);
        }

        const result = await importDrafts(
          email,
          password,
          body.rows,
          body.includeSignature !== false
        );

        return json({
          ok: true,
          ...result
        });
      }

      return json({ error: "API route not found." }, 404);

    } catch (err) {
      return json({
        error: err?.message || String(err)
      }, 500);
    }
  }
};
