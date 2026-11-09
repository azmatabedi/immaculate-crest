"""Email (SMTP) and WhatsApp (Meta Cloud API) notifications. Every attempt is logged in the notifications table."""
import re, smtplib, httpx
from email.message import EmailMessage
from . import config as C
from .db import SessionLocal
from .models import Notification, Document, Order

def _log(order_id, channel, to, subject, status, detail=""):
    with SessionLocal() as db:
        db.add(Notification(order_id=order_id, channel=channel, recipient=str(to)[:200], subject=(subject or "")[:200], status=status, detail=str(detail)[:1000]))
        db.commit()

def send_email(to, subject, body, order_id=None, attachments=None):
    if not to: return False
    if not (C.SMTP_HOST and C.SMTP_FROM):
        _log(order_id, "email", to, subject, "skipped", "SMTP is not configured"); return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = f"{C.COMPANY} <{C.SMTP_FROM}>", to, subject
    msg.set_content(body)
    for name, data in attachments or []:
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=name)
    try:
        if C.SMTP_PORT == 465:
            s = smtplib.SMTP_SSL(C.SMTP_HOST, C.SMTP_PORT, timeout=30)
        else:
            s = smtplib.SMTP(C.SMTP_HOST, C.SMTP_PORT, timeout=30); s.starttls()
        with s:
            if C.SMTP_USER: s.login(C.SMTP_USER, C.SMTP_PASS)
            s.send_message(msg)
        _log(order_id, "email", to, subject, "sent"); return True
    except Exception as e:
        _log(order_id, "email", to, subject, "failed", e); return False

def _wa_number(n):
    d = re.sub(r"\D", "", n or "")
    return "92" + d[1:] if d.startswith("0") and len(d) == 11 else d   # 03xx... -> Pakistan

def send_whatsapp(to, text=None, doc_url=None, filename=None, order_id=None):
    num = _wa_number(to)
    if not num: return False
    if not (C.WA_TOKEN and C.WA_PHONE_ID):
        _log(order_id, "whatsapp", num, text or filename, "skipped", "WhatsApp API is not configured"); return False
    body = {"messaging_product": "whatsapp", "to": num}
    if doc_url: body.update(type="document", document={"link": doc_url, "filename": filename, "caption": text or ""})
    else: body.update(type="text", text={"body": text})
    try:
        r = httpx.post(f"https://graph.facebook.com/v20.0/{C.WA_PHONE_ID}/messages", json=body,
                       headers={"Authorization": f"Bearer {C.WA_TOKEN}"}, timeout=30)
        ok = r.status_code < 300
        _log(order_id, "whatsapp", num, text or filename, "sent" if ok else "failed", "" if ok else r.text); return ok
    except Exception as e:
        _log(order_id, "whatsapp", num, text or filename, "failed", e); return False

SIGN = f"\n\nKind regards,\n{C.COMPANY} - the name of quality and trust\nWhatsApp: +92 336 8149077"

def order_received(s):
    kind = s["type"].lower()
    files = ("\nAttachments received: " + ", ".join(s["files"])) if s["files"] else ""
    send_email(s["email"], f"We received your {kind} {s['ref']}",
        f"Dear {s['name']},\n\nThank you for contacting {C.COMPANY}. We have received your {kind}.\n\nReference number: {s['ref']}\n"
        f"Product: {s['product']}\nQuantity: {s['qty']}{files}\n\nOur team will review your requirements and send you a quotation. "
        f"Please keep your reference number for any follow-up.{SIGN}", s["order_id"])
    send_email(C.ADMIN_EMAIL, f"New {kind}: {s['ref']} - {s['name']}",
        f"New {kind} {s['ref']}\n\nCustomer: {s['name']} ({s['company']})\nEmail: {s['email']}\nWhatsApp: {s['wa']}\nProduct: {s['product']}\n"
        f"Quantity: {s['qty']}\nCustomization: {s['custom']}\nNotes: {s['notes']}{files}\n\nOpen the dashboard: {C.BASE_URL}/admin/", s["order_id"])
    send_whatsapp(C.ADMIN_WHATSAPP, f"New {kind} {s['ref']}: {s['name']}, {s['product']} x {s['qty']}. Files: {len(s['files'])}. {C.BASE_URL}/admin/", order_id=s["order_id"])
    send_whatsapp(s["wa"], f"Hello {s['name']}, {C.COMPANY} received your {kind} {s['ref']}. We will review it and send a quotation soon.", order_id=s["order_id"])

def status_changed(s):
    send_email(s["email"], f"Update on your order {s['ref']}: {s['status']}",
        f"Dear {s['name']},\n\nThe status of your order {s['ref']} is now: {s['status']}.{SIGN}", s["order_id"])
    send_whatsapp(s["wa"], f"{C.COMPANY}: your order {s['ref']} is now '{s['status']}'.", order_id=s["order_id"])

def share_document(doc_id):
    """Email the PDF and send it over WhatsApp as a document link; records delivery status on the document."""
    with SessionLocal() as db:
        doc = db.get(Document, doc_id); order = db.get(Order, doc.order_id); cu = order.customer
        pdf = (C.DOCS_DIR / f"{doc.token}.pdf").read_bytes()
        title = doc.kind.title()
        ok_e = send_email(cu.email, f"{title} {doc.number} from {C.COMPANY}",
            f"Dear {cu.name},\n\nPlease find attached our {doc.kind} {doc.number} for order {order.reference}.\nYou can also download it here: {C.BASE_URL}/d/{doc.token}\n\n"
            f"Reply to this email or message us on WhatsApp to confirm or to request changes.{SIGN}", order.id, [(f"{doc.number}.pdf", pdf)])
        ok_w = send_whatsapp(cu.whatsapp, f"{title} {doc.number} for order {order.reference}", f"{C.BASE_URL}/d/{doc.token}", f"{doc.number}.pdf", order.id)
        doc.email_status, doc.whatsapp_status = ("sent" if ok_e else "failed"), ("sent" if ok_w else "failed")
        db.commit()
