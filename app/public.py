import re, random, string
from datetime import datetime
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, BackgroundTasks, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from . import config as C, notify
from .db import get_db
from .models import *
from .utils import row, limited, client_ip, save_upload, INQUIRY_EXT

router = APIRouter()
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def prod(p):
    d = row(p); d["category"] = p.category.name if p.category else None; d["media"] = [row(m) for m in p.media]; return d

@router.get("/api/products")
def products(db: Session = Depends(get_db)):
    q = db.query(Product).filter(Product.available == True).order_by(Product.sort_order, Product.id)
    return [prod(p) for p in q]

@router.get("/api/products/{pid}")
def product(pid: int, db: Session = Depends(get_db)):
    p = db.get(Product, pid)
    if not p or not p.available: raise HTTPException(404, "Not found")
    return prod(p)

@router.get("/api/categories")
def categories(db: Session = Depends(get_db)):
    return [row(c) for c in db.query(Category).order_by(Category.sort_order, Category.name)]

@router.get("/api/services")
def services(db: Session = Depends(get_db)):
    return [row(s) for s in db.query(Service).filter(Service.active == True).order_by(Service.sort_order, Service.id)]

@router.get("/api/articles")
def articles(db: Session = Depends(get_db)):
    return [row(a) for a in db.query(Article).filter(Article.published == True).order_by(Article.id.desc())]

@router.get("/api/reviews")
def reviews(db: Session = Depends(get_db)):
    return [row(r) for r in db.query(Review).filter(Review.approved == True).order_by(Review.id.desc()).limit(30)]

@router.post("/api/reviews")
def add_review(request: Request, name: str = Form(...), rating: int = Form(5), text: str = Form(...), company: str = Form(""), db: Session = Depends(get_db)):
    if limited("rv" + client_ip(request), 3, 3600): raise HTTPException(429, "Too many submissions, please try later")
    if not (1 <= rating <= 5) or not (3 <= len(text) <= 1500) or not name.strip(): raise HTTPException(400, "Please check your review")
    db.add(Review(name=name.strip()[:120], company=company[:160], rating=rating, text=text.strip(), approved=False)); db.commit()
    return {"message": "Thank you. Your review will appear after approval."}

@router.get("/api/factory-videos")
def factory(db: Session = Depends(get_db)):
    return [row(m) for m in db.query(Media).filter(Media.scope == "factory").order_by(Media.sort_order, Media.id)]

@router.get("/api/settings")
def settings(db: Session = Depends(get_db)):
    return {s.key: s.value for s in db.query(Setting).filter(Setting.key.in_(["etsy_links", "location", "stats"]))}

@router.post("/api/inquiries")
async def inquiry(request: Request, bg: BackgroundTasks, name: str = Form(...), email: str = Form(...), wa: str = Form(...),
                  qty: int = Form(...), product: str = Form(...), type: str = Form("Bulk inquiry"), company: str = Form(""),
                  custom: str = Form(""), extra: str = Form(""), website: str = Form(""),
                  files: list[UploadFile] = File(default=[]), db: Session = Depends(get_db)):
    if website: return {"reference": "IC-OK"}   # honeypot: bots fill hidden fields
    if limited("inq" + client_ip(request), 8, 3600): raise HTTPException(429, "Too many requests, please try again later")
    name, email, wa = name.strip(), email.strip().lower(), wa.strip()
    if not (1 <= len(name) <= 120) or not EMAIL.match(email) or len(email) > 190: raise HTTPException(400, "Please enter a valid name and email")
    if not (6 <= len(wa) <= 30) or not (1 <= qty <= 10_000_000) or not product.strip(): raise HTTPException(400, "Please check WhatsApp number, product and quantity")
    if type not in ("Bulk inquiry", "Sample request"): type = "Bulk inquiry"
    files = [f for f in files if f.filename]
    if len(files) > C.MAX_FILES: raise HTTPException(400, f"You can attach up to {C.MAX_FILES} files")
    saved = []
    try:
        for f in files:
            stored, size, _ = await save_upload(f, C.PRIVATE_DIR, INQUIRY_EXT, C.MAX_FILE_MB)
            saved.append((f.filename[:255], stored, size))
    except Exception:
        for _, st, _ in saved: (C.PRIVATE_DIR / st).unlink(missing_ok=True)
        raise
    cu = db.query(Customer).filter(Customer.email == email).first() or Customer(email=email)
    cu.name, cu.company, cu.whatsapp = name, company[:160], wa[:40]
    db.add(cu); db.flush()
    while True:
        ref = f"IC-{datetime.now():%Y%m%d}-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        if not db.query(Order).filter(Order.reference == ref).first(): break
    o = Order(reference=ref, customer_id=cu.id, type=type, product_name=product[:200], quantity=qty, customization=custom[:5000], notes=extra[:5000])
    pr = db.query(Product).filter(Product.name == product).first()
    o.items.append(OrderItem(product_id=pr.id if pr else None, product_name=product[:200], quantity=qty))
    for orig, st, size in saved: o.attachments.append(Attachment(original_name=orig, stored_name=st, size=size))
    db.add(o); db.commit()
    bg.add_task(notify.order_received, dict(order_id=o.id, ref=ref, type=type, name=name, company=company, email=email, wa=wa, product=product,
                qty=qty, custom=custom, notes=extra, files=[s[0] for s in saved]))
    return {"reference": ref}

@router.get("/d/{token}")
def public_document(token: str, db: Session = Depends(get_db)):
    d = db.query(Document).filter(Document.token == token).first()
    f = C.DOCS_DIR / f"{token}.pdf"
    if not d or not f.exists(): raise HTTPException(404, "Not found")
    return FileResponse(f, media_type="application/pdf", filename=f"{d.number}.pdf")
