from io import BytesIO
from decimal import Decimal
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from . import config as C

NAVY, GOLD, CREAM = colors.HexColor("#1C2733"), colors.HexColor("#B8935F"), colors.HexColor("#F5F1EA")
def esc(s): return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def m(v, cur): return f"{cur} {Decimal(str(v or 0)):,.2f}"

def build_pdf(doc, order, customer) -> bytes:
    buf = BytesIO()
    d = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm,
                          title=f"{doc.kind.title()} {doc.number}", author=C.COMPANY)
    b = ParagraphStyle("b", fontName="Helvetica", fontSize=9.5, leading=13)
    h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=20, textColor=NAVY, leading=24)
    w = ParagraphStyle("w", parent=b, textColor=colors.white, fontName="Helvetica-Bold")
    cur = doc.currency or "USD"
    head = Table([[Paragraph(f"<b>{esc(C.COMPANY)}</b>", ParagraphStyle("c", fontName="Helvetica-Bold", fontSize=16, textColor=NAVY)),
                   Paragraph(doc.kind.upper(), ParagraphStyle("k", fontName="Helvetica-Bold", fontSize=18, textColor=GOLD, alignment=2))],
                  [Paragraph("<br/>".join(esc(x) for x in C.COMPANY_LINES), b), ""]], colWidths=[100*mm, 74*mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, -1), (-1, -1), 1, GOLD), ("BOTTOMPADDING", (0, -1), (-1, -1), 8)]))
    meta = Table([[Paragraph(f"<b>Bill to</b><br/>{esc(customer.name)}<br/>{esc(customer.company)}<br/>{esc(customer.email)}<br/>{esc(customer.whatsapp)}", b),
                   Paragraph(f"<b>{doc.kind.title()} no.</b> {esc(doc.number)}<br/><b>Order reference</b> {esc(order.reference)}<br/>"
                             f"<b>Date</b> {doc.created_at:%d %b %Y}<br/><b>Revision</b> {doc.version}", b)]], colWidths=[87*mm, 87*mm])
    rows = [[Paragraph(x, w) for x in ("Description", "Qty", "Unit price", "Amount")]]
    for it in doc.items or []:
        q, u = Decimal(str(it.get("qty", 0))), Decimal(str(it.get("unit_price", 0)))
        rows.append([Paragraph(esc(it.get("description")), b), f"{q:g}", m(u, cur), m(q * u, cur)])
    t = Table(rows, colWidths=[84*mm, 18*mm, 34*mm, 38*mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("FONTSIZE", (0, 1), (-1, -1), 9.5),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CREAM]), ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#ddd5c5")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    tax = (Decimal(str(doc.subtotal)) * Decimal(str(doc.tax_percent or 0)) / 100).quantize(Decimal("0.01"))
    tot = [["Subtotal", m(doc.subtotal, cur)]]
    if doc.tax_percent: tot.append([f"Tax ({Decimal(str(doc.tax_percent)):g}%)", m(tax, cur)])
    if doc.extra_charges: tot.append([esc(doc.extra_note) or "Additional charges", m(doc.extra_charges, cur)])
    tot.append(["Total payable", m(doc.total, cur)])
    tt = Table(tot, colWidths=[134*mm, 40*mm], hAlign="RIGHT")
    tt.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "RIGHT"), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 1, GOLD)]))
    terms = doc.terms or ("Prices are valid for 14 days. Payment terms: 50% advance to confirm the order, balance before dispatch. "
                          "Sample approval is required before bulk production.")
    story = [head, Spacer(1, 8), meta, Spacer(1, 10), t, Spacer(1, 6), tt, Spacer(1, 14),
             Paragraph("<b>Payment terms and notes</b>", b), Paragraph(esc(terms), b), Spacer(1, 12),
             Paragraph(f"Thank you for choosing {esc(C.COMPANY)} - the name of quality and trust.", ParagraphStyle("f", parent=b, textColor=GOLD))]
    d.build(story)
    return buf.getvalue()
