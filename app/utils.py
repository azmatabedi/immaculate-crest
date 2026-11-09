import time, uuid
from pathlib import Path
from fastapi import HTTPException, Request, UploadFile

def row(o):
    return {c.name: getattr(o, c.name) for c in o.__table__.columns}

def clean(Model, data, allowed):
    out = {}
    for k in allowed:
        if k not in data:
            continue
        col, v = Model.__table__.c[k], data[k]
        pt = col.type.python_type
        if v in ("", None) and col.nullable:
            out[k] = None
        elif pt is bool:
            out[k] = v in (True, 1, "1", "true", "on")
        elif pt in (int, float):
            out[k] = pt(v)
        else:
            n = getattr(col.type, "length", None)
            out[k] = str(v)[:n] if n else str(v)
    return out

_hits = {}
def limited(key, n, window):
    t = time.time()
    h = [x for x in _hits.get(key, []) if t - x < window]
    if len(h) >= n:
        _hits[key] = h
        return True
    _hits[key] = h + [t]
    return False

def client_ip(request: Request):
    xf = request.headers.get("x-forwarded-for")
    return xf.split(",")[0].strip() if xf else (request.client.host if request.client else "?")

MAGIC = {
    "jpg": lambda h: h[:3] == b"\xff\xd8\xff", "jpeg": lambda h: h[:3] == b"\xff\xd8\xff",
    "png": lambda h: h[:8] == b"\x89PNG\r\n\x1a\n",
    "webp": lambda h: h[:4] == b"RIFF" and h[8:12] == b"WEBP",
    "avi": lambda h: h[:4] == b"RIFF" and h[8:12] == b"AVI ",
    "mp4": lambda h: h[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip"),
    "mov": lambda h: h[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip"),
    "webm": lambda h: h[:4] == b"\x1a\x45\xdf\xa3",
    "pdf": lambda h: h[:4] == b"%PDF",
    "doc": lambda h: h[:8] == bytes.fromhex("d0cf11e0a1b11ae1"),
    "docx": lambda h: h[:2] == b"PK",
}
INQUIRY_EXT = {"jpg", "jpeg", "png", "webp", "mp4", "mov", "avi", "pdf", "doc", "docx"}
MEDIA_EXT = {"jpg", "jpeg", "png", "webp", "mp4", "mov", "webm"}
VIDEO_EXT = {"mp4", "mov", "webm", "avi"}

async def save_upload(f: UploadFile, dest: Path, allowed, max_mb):
    """Validate extension + file signature + size, store under a random name."""
    ext = (f.filename or "").rsplit(".", 1)[-1].lower() if "." in (f.filename or "") else ""
    if ext not in allowed:
        raise HTTPException(400, f"File type not allowed: {f.filename}")
    stored, path, size = f"{uuid.uuid4().hex}.{ext}", None, 0
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / stored
    try:
        with open(path, "wb") as out:
            first = True
            while chunk := await f.read(1024 * 1024):
                if first:
                    if not MAGIC[ext](chunk[:16]):
                        raise HTTPException(400, f"File content does not match its type: {f.filename}")
                    first = False
                size += len(chunk)
                if size > max_mb * 1024 * 1024:
                    raise HTTPException(400, f"{f.filename} is larger than {max_mb} MB")
                out.write(chunk)
        if size == 0:
            raise HTTPException(400, f"Empty file: {f.filename}")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return stored, size, ext
