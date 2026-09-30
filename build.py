"""Build the test site: render templates/*.html with content/business.json into site/ (Python stdlib only).

Usage:  python build.py        (the host runs this on every commit; locally: py -3 build.py)
- One source per fact: every page and the LocalBusiness schema read from content/business.json.
- Clients can only change content/ (via the editor). templates/, this script, and config are Apex-only.
- Every value is HTML-escaped: content can't inject markup or scripts.
- Invalid content stops the build with exit 1, so the host keeps the previous live version.
- Photos: files the editor uploads to content/uploads/ are copied to site/images/uploads/. Each gallery photo must
  exist, be JPG/PNG/WebP, be at most MAX_IMAGE_MB, and have alt text.
Template syntax: {{ path.to.value }} (escaped) · <!-- each list -->…{{ item.x }}…<!-- /each --> · <!-- include partial.html -->
"""
import html, json, pathlib, re, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent
CONTENT, UPLOADS = ROOT / "content" / "business.json", ROOT / "content" / "uploads"
TEMPLATES, OUT = ROOT / "templates", ROOT / "site"
def normalize_phone(raw):
    """Accept common US formats (931-555-0100, 931.555.0100, +1 931 555 0100, …) → "(931) 555-0100", else None."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits[0] == "1": digits = digits[1:]
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}" if len(digits) == 10 else None

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_MB = 5
PUBLIC_UPLOADS = "/images/uploads/"

def validate(d):
    errs = []
    for key in ("business_name", "phone", "email", "address", "hours", "services"):
        if not d.get(key): errs.append(f"missing {key}")
    if d.get("phone") and not normalize_phone(d["phone"]): errs.append(f"phone '{d['phone']}' isn't a 10-digit US number")
    if d.get("email") and not EMAIL.match(d["email"]): errs.append(f"email '{d['email']}' isn't a valid address")
    if re.search("Ã.|â€", json.dumps(d, ensure_ascii=False)):  # UTF-8 text mis-decoded as Windows-1252
        errs.append("content contains garbled characters (e.g. 'â€“' instead of '–'); fix the text encoding")
    for i, s in enumerate(d.get("services", [])):
        if not s.get("name"): errs.append(f"services[{i}] has no name")
    for i, g in enumerate(d.get("gallery", [])):
        src, name = g.get("image", ""), pathlib.PurePosixPath(g.get("image", "")).name
        f = UPLOADS / name
        if not src.startswith(PUBLIC_UPLOADS) or not name: errs.append(f"gallery[{i}] image '{src}' isn't an uploaded photo")
        elif not f.is_file(): errs.append(f"gallery[{i}] photo '{name}' is missing from content/uploads/")
        elif f.suffix.lower() not in IMAGE_TYPES: errs.append(f"gallery[{i}] '{name}': use JPG, PNG, or WebP")
        elif f.stat().st_size > MAX_IMAGE_MB * 1024 * 1024: errs.append(f"gallery[{i}] '{name}' is over {MAX_IMAGE_MB} MB")
        if not g.get("alt"): errs.append(f"gallery[{i}] needs a short description (alt text)")
    return errs

def lookup(ctx, path):
    cur = ctx
    for part in path.split("."):
        cur = cur.get(part, "") if isinstance(cur, dict) else ""
    return cur

def render(tpl, ctx):
    tpl = re.sub(r"<!-- include ([\w.-]+) -->", lambda m: (TEMPLATES / "partials" / m.group(1)).read_text(encoding="utf-8"), tpl)
    def each(m):
        items = lookup(ctx, m.group(1)) or []
        return "".join(render(m.group(2), {**ctx, "item": it if isinstance(it, dict) else {"text": it}}) for it in items)
    tpl = re.sub(r"<!-- each ([\w.]+) -->(.*?)<!-- /each -->", each, tpl, flags=re.S)
    tpl = tpl.replace("{{{ jsonld }}}", ctx["_jsonld"])  # the only raw value: generated here, not typed by the client
    return re.sub(r"\{\{\s*([\w.]+)\s*\}\}", lambda m: html.escape(str(lookup(ctx, m.group(1)))), tpl)

def jsonld(d):
    data = {"@context": "https://schema.org", "@type": "BarberShop", "name": d["business_name"], "telephone": d["phone"],
            "email": d["email"], "address": d["address"],
            "openingHours": [f"{h['days']} {h['hours']}" for h in d["hours"]]}
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")  # can't close the <script> tag

def main():
    try:
        d = json.loads(CONTENT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"BUILD STOPPED: content/business.json can't be read ({e}); the live site keeps its previous version"); return 1
    errs = validate(d)
    if errs:
        print("BUILD STOPPED: content is invalid (the live site keeps its previous version):"); [print("  -", e) for e in errs]
        return 1
    d["gallery"] = [{**g, "src": PUBLIC_UPLOADS.lstrip("/") + pathlib.PurePosixPath(g["image"]).name} for g in d.get("gallery", [])]
    d["phone"] = normalize_phone(d["phone"])              # one display style everywhere, whatever format was typed
    d["phone_tel"] = "+1" + re.sub(r"\D", "", d["phone"])  # dialable form for tel: links, derived (never typed)
    ctx = {"business": d, "_jsonld": jsonld(d)}
    if OUT.exists(): shutil.rmtree(OUT)
    (OUT / "css").mkdir(parents=True)
    shutil.copy(TEMPLATES / "styles.css", OUT / "css" / "styles.css")
    shutil.copytree(UPLOADS, OUT / "images" / "uploads")
    for page in sorted(TEMPLATES.glob("*.html")):
        (OUT / page.name).write_text(render(page.read_text(encoding="utf-8"), ctx), encoding="utf-8")
    shutil.copytree(ROOT / "admin", OUT / "admin", ignore=shutil.ignore_patterns("backend-*.yml"))  # editor at /admin/ (noindex)
    # Trial: a second editor entrance per login method, same fields, different backend block.
    cfg = (ROOT / "admin" / "config.yml").read_text(encoding="utf-8")
    start, end = cfg.index("# BACKEND START"), cfg.index("# BACKEND END") + len("# BACKEND END")
    for backend in sorted((ROOT / "admin").glob("backend-*.yml")):
        name = backend.stem.split("-", 1)[1]
        dest = OUT / f"admin-{name}"; dest.mkdir()
        shutil.copy(ROOT / "admin" / "index.html", dest / "index.html")
        (dest / "config.yml").write_text(cfg[:start] + backend.read_text(encoding="utf-8") + cfg[end:], encoding="utf-8")
    print(f"built {len(list(TEMPLATES.glob('*.html')))} pages + {len(d['gallery'])} photos from content/ → site/")
    return 0

if __name__ == "__main__":
    sys.exit(main())
