import secrets
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, BackgroundTasks, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session
from . import config as C, notify
from .db import get_db
from .models import *
from .pdf import build_pdf
from .security import admin_required, check_pw, make_token
from .utils import row, clean, limited, client_ip, save_upload, MEDIA_EXT

router = APIRouter(prefix="/api/admin")
auth = [Depends(admin_required)]

class Login(BaseModel):
    username: str
    password: str

@router.post("/login")
def login(b: Login, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    if limited("login" + ip, 8, 900): raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
    u = db.query(AdminUser).filter(AdminUser.username == b.username).first()
    if not u or not check_pw(b.password, u.password_hash): raise HTTPException(401, "Wrong username or password")
    return {"token": make_token(u.username)}

@router.get("/stats", dependencies=auth)
def stats(db: Session = Depends(get_db)):
    c = lambda *s: db.query(Order).filter(Order.status.in_(s)).count()
    return {"total_inquiries": db.query(Order).count(), "new": c("New Inquiry"), "pending": c("New Inquiry", "Quotation Sent", "Awaiting Confirmation"),
            "confirmed": c("Confirmed", "In Production", "Dispatched"), "completed": c("Completed"), "products": db.query(Product).count(), "total_articles": db.query(Article).count(), "total_customers": db.query(Customer).count(),
            "pending_reviews": db.query(Review).filter(Review.approved == False).count()}

# ---------- orders ----------
@router.get("/orders", dependencies=auth)
def orders(status: str = "", q: str = "", db: Session = Depends(get_db)):
    qs = db.query(Order).join(Customer, Order.customer_id == Customer.id)
    if status: qs = qs.filter(Order.status == status)
    if q: qs = qs.filter(or_(Order.reference.like(f"%{q}%"), Customer.name.like(f"%{q}%"), Customer.company.like(f"%{q}%"), Customer.email.like(f"%{q}%")))
    return [dict(row(o), customer=row(o.customer), files=len(o.attachments)) for o in qs.order_by(Order.id.desc()).limit(300)]

@router.get("/orders/{oid}", dependencies=auth)
def order(oid: int, db: Session = Depends(get_db)):
    o = db.get(Order, oid)
    if not o: raise HTTPException(404, "Not found")
    nots = db.query(Notification).filter(Notification.order_id == oid).order_by(Notification.id.desc()).all()
    return dict(row(o), customer=row(o.customer), attachments=[row(a) for a in o.attachments], documents=[row(d) for d in o.documents],
                notifications=[row(n) for n in nots], statuses=C.STATUSES)

class StatusIn(BaseModel):
    status: str
    notify: bool = True

@router.patch("/orders/{oid}/status", dependencies=auth)
def set_status(oid: int, b: StatusIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    o = db.get(Order, oid)
    if not o or b.status not in C.STATUSES: raise HTTPException(400, "Invalid order or status")
    changed, o.status = o.status != b.status, b.status; db.commit()
    if changed and b.notify:
        cu = o.customer
        bg.add_task(notify.status_changed, dict(order_id=o.id, ref=o.reference, status=o.status, name=cu.name, email=cu.email, wa=cu.whatsapp))
    return {"status": o.status}

@router.get("/attachments/{aid}/download", dependencies=auth)
def download(aid: int, db: Session = Depends(get_db)):
    a = db.get(Attachment, aid)
    f = C.PRIVATE_DIR / (a.stored_name if a else "x")
    if not a or not f.exists(): raise HTTPException(404, "Not found")
    return FileResponse(f, filename=a.original_name)

# ---------- quotations & invoices ----------
class Item(BaseModel):
    description: str = Field(max_length=300)
    qty: float = Field(gt=0)
    unit_price: float = Field(ge=0)

class DocIn(BaseModel):
    kind: Literal["quotation", "invoice"] = "quotation"
    items: list[Item] = Field(min_length=1, max_length=50)
    tax_percent: float = Field(0, ge=0, le=100)
    extra_charges: float = Field(0, ge=0)
    extra_note: str = ""
    terms: str = ""
    currency: str = "USD"
    send: bool = False

def _make_pdf(db, doc):
    o = db.get(Order, doc.order_id)
    C.DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (C.DOCS_DIR / f"{doc.token}.pdf").write_bytes(build_pdf(doc, o, o.customer))

@router.post("/orders/{oid}/documents", dependencies=auth)
def new_document(oid: int, b: DocIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    o = db.get(Order, oid)
    if not o: raise HTTPException(404, "Not found")
    sub = sum((Decimal(str(i.qty)) * Decimal(str(i.unit_price)) for i in b.items), Decimal(0)).quantize(Decimal("0.01"))
    tax = (sub * Decimal(str(b.tax_percent)) / 100).quantize(Decimal("0.01"))
    total = sub + tax + Decimal(str(b.extra_charges))
    ver = db.query(Document).filter(Document.order_id == oid, Document.kind == b.kind).count() + 1
    d = Document(order_id=oid, kind=b.kind, version=ver, number=f"{'QT' if b.kind == 'quotation' else 'INV'}-{o.reference[3:]}-{ver}",
                 items=[i.model_dump() for i in b.items], subtotal=sub, tax_percent=b.tax_percent, extra_charges=b.extra_charges,
                 extra_note=b.extra_note[:200], total=total, currency=b.currency[:8].upper(), terms=b.terms, token=secrets.token_urlsafe(24))
    db.add(d); db.flush(); _make_pdf(db, d)
    if b.send:
        if b.kind == "quotation" and o.status == "New Inquiry": o.status = "Quotation Sent"
        db.commit(); bg.add_task(notify.share_document, d.id)
    else: db.commit()
    return row(d)

@router.post("/documents/{did}/send", dependencies=auth)
def resend(did: int, bg: BackgroundTasks, db: Session = Depends(get_db)):
    d = db.get(Document, did)
    if not d: raise HTTPException(404, "Not found")
    if d.kind == "quotation" and d.order_id and db.get(Order, d.order_id).status == "New Inquiry":
        db.get(Order, d.order_id).status = "Quotation Sent"; db.commit()
    d.email_status = d.whatsapp_status = "sending"; db.commit()
    bg.add_task(notify.share_document, d.id)
    return {"ok": True}

@router.get("/documents/{did}/pdf", dependencies=auth)
def doc_pdf(did: int, db: Session = Depends(get_db)):
    d = db.get(Document, did)
    if not d: raise HTTPException(404, "Not found")
    return FileResponse(C.DOCS_DIR / f"{d.token}.pdf", media_type="application/pdf", filename=f"{d.number}.pdf")

@router.get("/customers", dependencies=auth)
def customers(db: Session = Depends(get_db)):
    return [row(c) for c in db.query(Customer).order_by(Customer.id.desc()).limit(500)]

@router.get("/notifications", dependencies=auth)
def notifications(db: Session = Depends(get_db)):
    return [row(n) for n in db.query(Notification).order_by(Notification.id.desc()).limit(200)]

# ---------- generic CRUD for simple tables ----------
def crud(path, Model, fields, order=None):
    r = APIRouter(prefix=f"/{path}", dependencies=auth)
    @r.get("")
    def lst(db: Session = Depends(get_db)):
        return [row(x) for x in db.query(Model).order_by(order if order is not None else Model.id.desc())]
    @r.post("")
    def add(b: dict, db: Session = Depends(get_db)):
        x = Model(**clean(Model, b, fields)); db.add(x); db.commit(); return row(x)
    @r.put("/{i}")
    def upd(i: int, b: dict, db: Session = Depends(get_db)):
        x = db.get(Model, i)
        if not x: raise HTTPException(404, "Not found")
        for k, v in clean(Model, b, fields).items(): setattr(x, k, v)
        db.commit(); return row(x)
    @r.delete("/{i}")
    def rm(i: int, db: Session = Depends(get_db)):
        x = db.get(Model, i)
        if x: db.delete(x); db.commit()
        return {"ok": True}
    router.include_router(r)

crud("categories", Category, ["name", "sort_order"], Category.sort_order)
crud("services", Service, ["title", "description", "active", "sort_order"], Service.sort_order)
crud("articles", Article, ["title", "body", "published"])
crud("reviews", Review, ["name", "company", "rating", "text", "approved"])

# ---------- products and media ----------
PFIELDS = ["category_id", "name", "description", "specs", "customization", "moq", "etsy_url", "available", "sort_order"]
def _pd(p): d = row(p); d["media"] = [row(m) for m in p.media]; return d

@router.get("/products", dependencies=auth)
def plist(db: Session = Depends(get_db)):
    return [_pd(p) for p in db.query(Product).order_by(Product.sort_order, Product.id)]

@router.post("/products", dependencies=auth)
def padd(b: dict, db: Session = Depends(get_db)):
    p = Product(**clean(Product, b, PFIELDS)); db.add(p); db.commit(); return _pd(p)

@router.put("/products/{pid}", dependencies=auth)
def pupd(pid: int, b: dict, db: Session = Depends(get_db)):
    p = db.get(Product, pid)
    if not p: raise HTTPException(404, "Not found")
    for k, v in clean(Product, b, PFIELDS).items(): setattr(p, k, v)
    db.commit(); return _pd(p)

@router.delete("/products/{pid}", dependencies=auth)
def pdel(pid: int, db: Session = Depends(get_db)):
    p = db.get(Product, pid)
    if p:
        for m in p.media: (C.PUBLIC_DIR / m.path).unlink(missing_ok=True)
        db.delete(p); db.commit()
    return {"ok": True}

async def _upload(files, db, scope, product_id=None, title=""):
    n = db.query(Media).filter(Media.scope == scope, Media.product_id == product_id).count()
    out = []
    for f in files:
        ext = (f.filename or "").rsplit(".", 1)[-1].lower()
        stored, _, ext = await save_upload(f, C.PUBLIC_DIR, MEDIA_EXT, C.MAX_VIDEO_MB if ext in ("mp4", "mov", "webm") else C.MAX_FILE_MB)
        m = Media(product_id=product_id, scope=scope, kind="video" if ext in ("mp4", "mov", "webm") else "image", path=stored,
                  title=title or (f.filename or "")[:200], sort_order=n); n += 1
        db.add(m); out.append(m)
    db.commit(); return [row(m) for m in out]

@router.post("/products/{pid}/media", dependencies=auth)
async def padd_media(pid: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    if not db.get(Product, pid): raise HTTPException(404, "Not found")
    return await _upload(files, db, "product", pid)

@router.post("/factory-videos", dependencies=auth)
async def fadd(files: list[UploadFile] = File(...), title: str = Form(""), db: Session = Depends(get_db)):
    return await _upload(files, db, "factory", None, title)

@router.patch("/media/{mid}", dependencies=auth)
def mupd(mid: int, b: dict, db: Session = Depends(get_db)):
    m = db.get(Media, mid)
    if not m: raise HTTPException(404, "Not found")
    for k, v in clean(Media, b, ["title", "sort_order"]).items(): setattr(m, k, v)
    db.commit(); return row(m)

@router.delete("/media/{mid}", dependencies=auth)
def mdel(mid: int, db: Session = Depends(get_db)):
    m = db.get(Media, mid)
    if m: (C.PUBLIC_DIR / m.path).unlink(missing_ok=True); db.delete(m); db.commit()
    return {"ok": True}

# ---------- site settings (Etsy links etc.) ----------
@router.get("/settings", dependencies=auth)
def get_settings(db: Session = Depends(get_db)):
    return {s.key: s.value for s in db.query(Setting)}

@router.put("/settings/{key}", dependencies=auth)
def put_setting(key: str, b: dict, db: Session = Depends(get_db)):
    if key not in ("etsy_links", "location", "stats"): raise HTTPException(400, "Unknown setting")
    s = db.get(Setting, key) or Setting(key=key); s.value = b.get("value"); db.add(s); db.commit(); return {"ok": True}
