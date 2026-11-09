import time, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from . import config as C
from .db import Base, engine, SessionLocal
from .models import *
from .security import hash_pw
from . import public, admin

log = logging.getLogger("uvicorn.error")

SERVICES = [("Customize leather manufacturing", "Bags, wallets, jackets, purses and duffels built to your specification."),
 ("Leather QC check", "Quality-control inspection of leather, stitching and finish before goods ship."),
 ("Corporate and branded gifts", "Logo embossing, engraving and foil stamping for company gift programs."),
 ("E-commerce store development", "Storefronts built and launched for new and existing brands."),
 ("Store audits and account management", "Etsy, Amazon and eBay audits that show why sales are not coming."),
 ("Catalog and listing optimization", "SEO titles, tags, photos and listings built to convert."),
 ("Packaging and global logistics", "Branded packaging, warehousing and worldwide fulfillment.")]
PRODUCTS = [("Bags", "Diamond patchwork cowhide backpack", "Hairon cowhide backpack, laptop-ready."),
 ("Bags", "Cowhide duffle weekender", "Black and white hairon travel bag."), ("Bags", "Hairon leather tote bag", "Western patchwork everyday tote."),
 ("Bags", "Luxury black leather backpack", "Work and travel backpack."), ("Home decor", "Tri-color cowhide rug", "Natural hairon rug for home decor."),
 ("Home decor", "Engraved cowhide rug with logo", "Corporate branding option."), ("Gifts", "Personalized cowhide backpack", "Custom gift orders."),
 ("Bags", "Patchwork boho backpack", "Western hairon travel bag.")]

ETSY = [
 {"name": "Immaculate Crest", "url": "https://www.etsy.com/shop/IMMACULATECREST", "note": "Our direct store"},
 {"name": "Hideor", "url": "https://www.etsy.com/shop/Hideor", "note": "Bags and everyday carry"},
 {"name": "RealChamra", "url": "https://www.etsy.com/uk/shop/RealChamra", "note": "Rugs, decor and personalized gifts"},
 {"name": "CowhidecraftCo", "url": "https://www.etsy.com/shop/CowhidecraftCo", "note": "Cowhide duffle bags and leather goods"}]
OLD_ETSY_NAMES = ["Immaculate Crest", "Hideor", "RealChamra"]

STATS = {"countries": 5, "instagram": {"handle": "8immaculatecrest", "posts": None, "followers": None},
 "shops": [{"name": "Hideor", "sales": 54, "rating": 4.2, "reviews": 10, "months": 18},
           {"name": "RealChamra", "sales": 44, "rating": 4.1, "reviews": 6, "months": 12},
           {"name": "CowhidecraftCo", "sales": 15, "rating": 5.0, "reviews": 3, "months": 9},
           {"name": "Immaculate Crest", "sales": 2, "rating": None, "reviews": 0, "months": 2}],
 "items": [{"name": "Duffle bags", "shop": "CowhidecraftCo", "listings": 30, "sales": None, "price": 160},
           {"name": "Backpacks", "shop": "CowhidecraftCo", "listings": 13, "sales": None, "price": 143},
           {"name": "Cowhide rugs", "shop": "CowhidecraftCo", "listings": 9, "sales": None, "price": None},
           {"name": "Patchwork rugs", "shop": "CowhidecraftCo", "listings": 4, "sales": None, "price": None},
           {"name": "Tote bags", "shop": "CowhidecraftCo", "listings": 3, "sales": None, "price": 130}],
 "monthly": []}

def seed():
    with SessionLocal() as db:
        if C.ADMIN_PASSWORD and not db.query(AdminUser).first():
            db.add(AdminUser(username=C.ADMIN_USERNAME, password_hash=hash_pw(C.ADMIN_PASSWORD)))
        if not db.query(Service).first():
            db.add_all(Service(title=t, description=d, sort_order=i) for i, (t, d) in enumerate(SERVICES))
        if not db.query(Product).first():
            cats = {n: Category(name=n, sort_order=i) for i, n in enumerate(["Bags", "Home decor", "Gifts"])}
            db.add_all(cats.values()); db.flush()
            db.add_all(Product(category_id=cats[c].id, name=n, description=d, moq=50, sort_order=i,
                               specs="Genuine cowhide leather\nSize and color on request", customization="Logo embossing, engraving, foil stamping, private-label packaging")
                       for i, (c, n, d) in enumerate(PRODUCTS))
        es = db.get(Setting, "etsy_links")
        if not es: db.add(Setting(key="etsy_links", value=ETSY))
        elif [x.get("name") for x in (es.value or [])] == OLD_ETSY_NAMES: es.value = ETSY   # upgrade the untouched default list
        if not db.get(Setting, "stats"): db.add(Setting(key="stats", value=STATS))
        if not db.get(Setting, "location"):
            db.add(Setting(key="location", value={"label": "Immaculate Crest, Karachi, Pakistan", "query": "Karachi, Pakistan", "embed_url": "", "link": ""}))
        db.commit()

@asynccontextmanager
async def lifespan(app):
    if C.SECRET_KEY != "change-me" and not C.DEBUG:
        raise RuntimeError("Set a strong SECRET_KEY in .env before starting")
    for d in (C.PUBLIC_DIR, C.PRIVATE_DIR, C.DOCS_DIR): d.mkdir(parents=True, exist_ok=True)
    for i in range(30):   # wait for MySQL to accept connections
        try:
            Base.metadata.create_all(engine); break
        except Exception as e:
            log.warning("Database not ready (%s), retrying...", e); time.sleep(2)
    else:
        raise RuntimeError("Database unavailable")
    seed()
    yield

app = FastAPI(title="Immaculate Crest", lifespan=lifespan, docs_url="/docs" if C.DEBUG else None, redoc_url=None, openapi_url="/openapi.json" if C.DEBUG else None)

@app.middleware("http")
async def headers(request: Request, call_next):
    r = await call_next(request)
    r.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "strict-origin-when-cross-origin",
        "Content-Security-Policy": "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; "
                                   "script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-src https://www.google.com; frame-ancestors 'none'"})
    return r

app.include_router(public.router)
app.include_router(admin.router)
for _d in (C.PUBLIC_DIR, C.PRIVATE_DIR, C.DOCS_DIR): _d.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=C.PUBLIC_DIR), name="media")
app.mount("/", StaticFiles(directory="static", html=True), name="site")
