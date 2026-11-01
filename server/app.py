import json, os, sqlite3, threading, time
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify

DB = os.environ.get("DB", "rebajon.db")
EVERY_MIN = int(os.environ.get("EVERY_MIN", "30"))
HDR = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36",
       "Accept-Language": "es-ES,es;q=0.9"}
app = Flask(__name__)


def db():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT, category TEXT);
        CREATE TABLE IF NOT EXISTS links(id INTEGER PRIMARY KEY, product_id INTEGER, store TEXT, url TEXT);
        CREATE TABLE IF NOT EXISTS prices(link_id INTEGER, price REAL, ts INTEGER);
        CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, title TEXT, body TEXT, ts INTEGER);
        CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);""")


def num(x):
    try:
        s = str(x).strip().replace("\xa0", "").replace("€", "").strip()
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        v = float(s)
        return v if v > 0 else None
    except Exception:
        return None


def find_price(o):
    if isinstance(o, list):
        for i in o:
            r = find_price(i)
            if r:
                return r
    elif isinstance(o, dict):
        for k in ("price", "lowPrice"):
            if k in o and num(o[k]):
                return num(o[k])
        for v in o.values():
            if isinstance(v, (list, dict)):
                r = find_price(v)
                if r:
                    return r
    return None


def get_price(url):
    """Extrae el precio de JSON-LD, meta tags o selector de Amazon. Devuelve None si falla/bloquean."""
    try:
        r = requests.get(url, headers=HDR, timeout=20)
        if r.status_code != 200:
            return None
        s = BeautifulSoup(r.text, "html.parser")
        for t in s.find_all("script", type="application/ld+json"):
            try:
                p = find_price(json.loads(t.string or ""))
            except Exception:
                p = None
            if p:
                return p
        for sel in ({"property": "product:price:amount"}, {"itemprop": "price"}):
            m = s.find(attrs=sel)
            if m:
                p = num(m.get("content") or m.get_text())
                if p:
                    return p
        m = s.select_one("span.a-price span.a-offscreen")
        if m:
            return num(m.get_text())
    except Exception:
        pass
    return None


def store_of(url):
    parts = urlparse(url).netloc.lower().replace("www.", "").split(".")
    return parts[-2] if len(parts) >= 2 else parts[0]


def cfg():
    d = {"min_drop": "15", "stores": "", "categories": ""}
    with db() as c:
        for r in c.execute("SELECT k,v FROM settings"):
            d[r["k"]] = r["v"]
    return d


def check_all():
    now = int(time.time())
    st = cfg()
    md = float(st["min_drop"] or 15)
    stores = [x for x in st["stores"].split(",") if x]
    cats = [x.strip().lower() for x in st["categories"].split(",") if x.strip()]
    with db() as c:
        rows = c.execute("SELECT l.id,l.store,l.url,p.name,p.category FROM links l JOIN products p ON p.id=l.product_id").fetchall()
        for l in rows:
            price = get_price(l["url"])
            time.sleep(2)
            if price is None:
                continue
            prev = c.execute("SELECT price FROM prices WHERE link_id=? ORDER BY ts DESC LIMIT 1", (l["id"],)).fetchone()
            ref = c.execute("SELECT MAX(price) m FROM prices WHERE link_id=? AND ts>?", (l["id"], now - 30 * 86400)).fetchone()["m"]
            c.execute("INSERT INTO prices VALUES(?,?,?)", (l["id"], price, now))
            if not prev or not ref or price >= prev["price"]:
                continue
            drop = (ref - price) / ref * 100
            if drop < md:
                continue
            if stores and l["store"] not in stores:
                continue
            if cats and (l["category"] or "").lower() not in cats:
                continue
            c.execute("INSERT INTO alerts(title,body,ts) VALUES(?,?,?)",
                      (f"-{drop:.0f}% {l['name']}", f"{price:.2f} € en {l['store']} (antes {ref:.2f} €)", now))


def loop():
    while True:
        try:
            check_all()
        except Exception as e:
            print("check error:", e)
        time.sleep(EVERY_MIN * 60)


@app.after_request
def cors(r):
    r.headers["Access-Control-Allow-Origin"] = "*"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    r.headers["Access-Control-Allow-Methods"] = "GET,POST,DELETE,OPTIONS"
    return r


@app.get("/products")
def products():
    out = []
    with db() as c:
        for p in c.execute("SELECT * FROM products ORDER BY id DESC").fetchall():
            links = []
            for l in c.execute("SELECT * FROM links WHERE product_id=?", (p["id"],)).fetchall():
                h = [[r["ts"], r["price"]] for r in c.execute("SELECT ts,price FROM prices WHERE link_id=? ORDER BY ts", (l["id"],))]
                links.append({"store": l["store"], "url": l["url"], "history": h,
                              "price": h[-1][1] if h else None, "min": min(x[1] for x in h) if h else None})
            out.append({"id": p["id"], "name": p["name"], "category": p["category"], "links": links})
    return jsonify(out)


@app.post("/products")
def add_product():
    b = request.get_json(force=True)
    urls = [u for u in b.get("urls", []) if u.startswith("http")]
    if not b.get("name") or not urls:
        return jsonify(error="datos incompletos"), 400
    with db() as c:
        pid = c.execute("INSERT INTO products(name,category) VALUES(?,?)", (b["name"], b.get("category", ""))).lastrowid
        for u in urls:
            c.execute("INSERT INTO links(product_id,store,url) VALUES(?,?,?)", (pid, store_of(u), u))
    threading.Thread(target=check_all, daemon=True).start()
    return jsonify(id=pid)


@app.delete("/products/<int:pid>")
def del_product(pid):
    with db() as c:
        ids = [r["id"] for r in c.execute("SELECT id FROM links WHERE product_id=?", (pid,))]
        for i in ids:
            c.execute("DELETE FROM prices WHERE link_id=?", (i,))
        c.execute("DELETE FROM links WHERE product_id=?", (pid,))
        c.execute("DELETE FROM products WHERE id=?", (pid,))
    return jsonify(ok=True)


@app.get("/settings")
def get_settings():
    return jsonify(cfg())


@app.post("/settings")
def set_settings():
    b = request.get_json(force=True)
    with db() as c:
        for k in ("min_drop", "stores", "categories"):
            if k in b:
                c.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, str(b[k])))
    return jsonify(ok=True)


@app.get("/alerts")
def alerts():
    since = request.args.get("since", 0, type=int)
    with db() as c:
        return jsonify([dict(r) for r in c.execute("SELECT * FROM alerts WHERE id>? ORDER BY id", (since,))])


if __name__ == "__main__":
    init()
    threading.Thread(target=loop, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)
