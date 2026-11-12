from __future__ import annotations

import json
import os
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import agent

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("DATABASE_PATH", ROOT / "data" / "cartgenii.db"))
STATIC = ROOT / "frontend"
CURRENCY = os.getenv("APP_CURRENCY", "USD").upper()
app = FastAPI(title="CartGenii", version="1.0.0", description="AI-assisted procurement with PayPal Sandbox checkout")
app.add_middleware(CORSMiddleware, allow_origins=[os.getenv("FRONTEND_ORIGIN", "*")], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
app.mount("/assets", StaticFiles(directory=STATIC), name="assets")

SEED = [
    ("laptop-air-14", "Aster Air 14 Laptop", "Electronics", "Lightweight laptop for coding, study and everyday work.", {"ram_gb": 16, "storage_gb": 512, "display_in": 14, "use": "programming"}, "Northstar Supply", 79900, 18, 1),
    ("laptop-pro-15", "Aster Pro 15 Laptop", "Electronics", "Higher-performance laptop with a larger display and fast storage.", {"ram_gb": 16, "storage_gb": 1024, "display_in": 15, "use": "programming"}, "Pixel Depot", 88900, 8, 1),
    ("laptop-core-14", "Nova Core 14 Laptop", "Electronics", "Balanced 14-inch machine with ample memory for development.", {"ram_gb": 16, "storage_gb": 512, "display_in": 14, "use": "programming"}, "Northstar Supply", 82900, 25, 1),
    ("laptop-studio-16", "Nova Studio 16 Laptop", "Electronics", "Large-screen workstation for demanding creative tasks.", {"ram_gb": 32, "storage_gb": 1024, "display_in": 16, "use": "creative"}, "Pixel Depot", 119900, 6, 1),
    ("shirt-black-cotton", "Everyday Cotton T-Shirt", "Apparel", "Soft black 100% cotton crew-neck T-shirt. Sizes S to XL.", {"colour": "black", "material": "cotton", "sizes": ["S", "M", "L", "XL"]}, "Threadline Wholesale", 425, 480, 25),
    ("shirt-black-organic", "Organic Cotton T-Shirt", "Apparel", "Black certified-organic cotton shirt in sizes S to XL.", {"colour": "black", "material": "organic cotton", "sizes": ["S", "M", "L", "XL"]}, "Green Stitch Co.", 475, 320, 20),
    ("shirt-black-poly", "Performance T-Shirt", "Apparel", "Black quick-dry performance blend. Sizes S to XL.", {"colour": "black", "material": "polyester blend", "sizes": ["S", "M", "L", "XL"]}, "Threadline Wholesale", 350, 600, 50),
    ("shirt-white-cotton", "Everyday Cotton T-Shirt — White", "Apparel", "Soft white 100% cotton crew-neck T-shirt. Sizes S to XL.", {"colour": "white", "material": "cotton", "sizes": ["S", "M", "L", "XL"]}, "Green Stitch Co.", 400, 260, 25),
    ("notebook-a5", "A5 Recycled Notebook", "Stationery", "Ruled 160-page notebook made with recycled paper.", {"size": "A5", "pages": 160, "material": "recycled paper"}, "Paper & Pine", 325, 900, 10),
    ("pen-gel-black", "Black Gel Pen (Pack of 10)", "Stationery", "Smooth-writing black gel pens for office and school.", {"colour": "black", "pack_size": 10, "type": "gel"}, "Paper & Pine", 550, 700, 10),
    ("headphones-wireless", "Horizon Wireless Headphones", "Electronics", "Comfortable over-ear wireless headphones with noise reduction.", {"type": "wireless", "noise_cancelling": True}, "Pixel Depot", 12900, 40, 1),
    ("monitor-27", "Viewpoint 27-inch Monitor", "Electronics", "QHD monitor with an adjustable stand for home offices.", {"display_in": 27, "resolution": "QHD"}, "Northstar Supply", 22900, 14, 1),
    ("laptop-air-14-pd", "Aster Air 14 Laptop", "Electronics", "Lightweight laptop for coding, study and everyday work.", {"ram_gb": 16, "storage_gb": 512, "display_in": 14, "use": "programming"}, "Pixel Depot", 81500, 30, 1),
    ("laptop-flex-13", "Lumen Flex 13 Laptop", "Electronics", "Ultra-portable 13-inch laptop with long battery life; 8 GB memory.", {"ram_gb": 8, "storage_gb": 512, "display_in": 13, "use": "everyday"}, "Northstar Supply", 54900, 22, 1),
    ("laptop-dev-14", "Kepler Dev 14 Laptop", "Electronics", "Developer laptop with 32 GB memory and a sharp 14-inch display.", {"ram_gb": 32, "storage_gb": 512, "display_in": 14, "use": "programming"}, "Circuit Hub", 94900, 9, 1),
    ("laptop-value-15", "Nova Value 15 Laptop", "Electronics", "Budget 15-inch laptop for study and office work.", {"ram_gb": 8, "storage_gb": 256, "display_in": 15, "use": "everyday"}, "Circuit Hub", 44900, 35, 1),
    ("laptop-core-14-ch", "Nova Core 14 Laptop", "Electronics", "Balanced 14-inch machine with ample memory for development.", {"ram_gb": 16, "storage_gb": 512, "display_in": 14, "use": "programming"}, "Circuit Hub", 84500, 4, 1),
    ("shirt-black-cotton-bm", "Everyday Cotton T-Shirt", "Apparel", "Soft black 100% cotton crew-neck T-shirt. Sizes S to XL.", {"colour": "black", "material": "cotton", "sizes": ["S", "M", "L", "XL"]}, "Bulk Merch Direct", 399, 150, 50),
    ("shirt-black-heavy", "Heavyweight Cotton T-Shirt", "Apparel", "Premium 220 gsm black cotton tee for uniforms. Sizes S to XXL.", {"colour": "black", "material": "cotton", "sizes": ["S", "M", "L", "XL", "XXL"]}, "Bulk Merch Direct", 610, 900, 50),
    ("shirt-navy-cotton", "Everyday Cotton T-Shirt — Navy", "Apparel", "Navy 100% cotton crew-neck T-shirt. Sizes S to XL.", {"colour": "navy", "material": "cotton", "sizes": ["S", "M", "L", "XL"]}, "Threadline Wholesale", 430, 400, 25),
    ("shirt-black-polo", "Cotton Polo Shirt", "Apparel", "Black cotton pique polo for staff uniforms. Sizes S to XL.", {"colour": "black", "material": "cotton", "sizes": ["S", "M", "L", "XL"]}, "Green Stitch Co.", 899, 200, 20),
    ("notebook-a5-office", "A5 Hardcover Notebook", "Stationery", "Ruled 192-page hardcover notebook for office teams.", {"size": "A5", "pages": 192, "material": "paper"}, "Office Point", 410, 1200, 20),
    ("notebook-a4-spiral", "A4 Spiral Notebook", "Stationery", "Ruled 120-page spiral notebook.", {"size": "A4", "pages": 120, "material": "paper"}, "Office Point", 290, 600, 25),
    ("pen-gel-black-op", "Black Gel Pen (Pack of 10)", "Stationery", "Smooth-writing black gel pens for office and school.", {"colour": "black", "pack_size": 10, "type": "gel"}, "Office Point", 499, 300, 20),
    ("pen-ball-blue", "Blue Ballpoint Pen (Pack of 20)", "Stationery", "Everyday blue ballpoint pens in a bulk pack.", {"colour": "blue", "pack_size": 20, "type": "ballpoint"}, "Paper & Pine", 380, 800, 10),
    ("headphones-studio", "Horizon Studio Headphones", "Electronics", "Wired studio headphones with a flat, accurate sound.", {"type": "wired", "noise_cancelling": False}, "Circuit Hub", 8900, 25, 1),
    ("monitor-24", "Viewpoint 24-inch Monitor", "Electronics", "Full-HD 24-inch monitor for everyday work.", {"display_in": 24, "resolution": "FHD"}, "Circuit Hub", 13900, 30, 1),
]

@contextmanager
def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS listings(id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, description TEXT NOT NULL, attributes TEXT NOT NULL, supplier TEXT NOT NULL, unit_cents INTEGER NOT NULL, stock INTEGER NOT NULL, min_qty INTEGER NOT NULL, currency TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, mode TEXT NOT NULL, status TEXT NOT NULL, currency TEXT NOT NULL, total_cents INTEGER NOT NULL, paypal_order_id TEXT, created_at TEXT NOT NULL, items TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS payments(id TEXT PRIMARY KEY, order_id TEXT NOT NULL, paypal_order_id TEXT, status TEXT NOT NULL, amount_cents INTEGER NOT NULL, currency TEXT NOT NULL, created_at TEXT NOT NULL, captured_at TEXT);
        """)
        # INSERT OR IGNORE keeps existing rows (and demo stock) but adds any new seed listings.
        if True:
            c.executemany("INSERT OR IGNORE INTO listings VALUES(?,?,?,?,?,?,?,?,?,?)", [(i,n,cat,d,json.dumps(a),s,p,stock,m,CURRENCY) for i,n,cat,d,a,s,p,stock,m in SEED])
init_db()

def row_item(r):
    d = dict(r); d["attributes"] = json.loads(d.pop("attributes")); d["unit_price"] = f"{d.pop('unit_cents') / 100:.2f}"; d["currency"] = d.get("currency", CURRENCY); return d

def paypal_configured():
    client_id=os.getenv("PAYPAL_CLIENT_ID", "").strip()
    secret=os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
    return bool(client_id and secret and not client_id.lower().startswith("your_") and not secret.lower().startswith("your_"))

def ai_configured():
    return agent.llm_configured()

def dollars_to_cents(value) -> int:
    try: return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception: raise HTTPException(422, "Budget must be a valid amount")

class ParseRequest(BaseModel):
    mode: Literal["individual", "business"]
    message: str = Field(min_length=3, max_length=1200)

class OrderLine(BaseModel):
    listing_id: str
    quantity: int = Field(ge=1, le=10000)

class OrderRequest(BaseModel):
    mode: Literal["individual", "business"]
    items: list[OrderLine] = Field(min_length=1, max_length=20)

def heuristic_parse(mode: str, message: str):
    text = message.lower()
    budget_match = re.search(r"(?:under|below|budget(?: of)?|within|less than|up to)\s*\$?\s*(\d[\d,]*(?:\.\d{1,2})?)", text)
    if mode == "business":
        qty_match = re.search(r"\b(\d{1,5})\s+(?:(?:black|white|cotton|organic|small|medium|large|size|xs|s|m|l|xl)\s+){0,4}(?:t-?shirts?|shirts?|units?|pieces?|pcs|items?|notebooks?|pens?)\b", text)
        qty = int(qty_match.group(1)) if qty_match and int(qty_match.group(1)) > 1 else 100
        category = "apparel" if any(x in text for x in ("shirt", "apparel", "clothing", "t-shirt")) else "stationery" if any(x in text for x in ("notebook", "pen", "stationery")) else "electronics"
        specs = {"colour": "black"} if "black" in text else {}
        if "cotton" in text: specs["material"] = "cotton"
        sizes = [x.upper() for x in re.findall(r"\b(xs|s|m|l|xl|xxl)\b", text)]
        if sizes: specs["sizes"] = sizes
        query = "t-shirt" if category == "apparel" else "notebook" if category == "stationery" else "laptop"
    else:
        qty = 1
        category = "electronics" if any(x in text for x in ("laptop", "computer", "headphone", "monitor")) else "stationery" if any(x in text for x in ("notebook", "pen")) else "apparel"
        specs = {}
        ram = re.search(r"(\d+)\s*gb\s*ram", text)
        storage = re.search(r"(\d+)\s*gb\s*(?:ssd|storage)", text)
        if ram: specs["ram_gb"] = int(ram.group(1))
        if storage: specs["storage_gb"] = int(storage.group(1))
        query = "laptop" if category == "electronics" else "notebook" if category == "stationery" else "t-shirt"
    budget = float(budget_match.group(1).replace(",", "")) if budget_match else None
    return {"mode": mode, "category": category, "product_query": query, "quantity": qty, "budget": budget, "currency": CURRENCY, "specifications": specs}

def matches(req, item):
    cat = (req.get("category") or "").lower()
    if cat and cat not in item["category"].lower() and not (cat == "apparel" and item["category"] == "Apparel"): return False
    query = (req.get("product_query") or "").lower()
    if query and not any(w in (item["name"] + " " + item["description"]).lower() for w in query.split() if len(w) > 2): return False
    attrs = item["attributes"]; specs = req.get("specifications") or {}
    for k,v in specs.items():
        if k not in attrs: continue
        av=attrs[k]
        if isinstance(v, list):
            if not set(map(str.lower,map(str,v))).issubset(set(map(str.lower,map(str,av if isinstance(av,list) else [av])))): return False
        elif isinstance(v, (int,float)):
            if not isinstance(av,(int,float)) or av < v: return False
        elif str(v).lower() not in str(av).lower(): return False
    qty = int(req.get("quantity") or 1)
    if item["stock"] < qty or item["min_qty"] > qty: return False
    if req.get("budget") is not None and dollars_to_cents(item["unit_price"])*qty > dollars_to_cents(req["budget"]): return False
    return True

def search_for(req):
    with db() as c: rows=[row_item(r) for r in c.execute("SELECT * FROM listings ORDER BY unit_cents")]
    eligible=[x for x in rows if matches(req,x)]
    qty=max(1,int(req.get("quantity") or 1))
    for x in eligible:
        total=int(Decimal(x["unit_price"])*100)*qty
        x["line_total"] = f"{total/100:.2f}"
        x["quantity"] = qty
        x["reason"] = f"In stock for {qty} unit{'s' if qty != 1 else ''}; ${x['unit_price']} each from {x['supplier']}."
    return eligible

@app.get("/")
def home(): return FileResponse(STATIC / "index.html")

@app.get("/api/health")
def health(): return {"status":"ok","app":"CartGenii","ai_configured":ai_configured(),"ai_provider":agent.llm_label(),"paypal_configured":paypal_configured(),"client_id":os.getenv("PAYPAL_CLIENT_ID") if paypal_configured() else None,"currency":CURRENCY}

@app.get("/api/products")
def products(category: str | None = None, q: str | None = None):
    with db() as c: rows=[row_item(r) for r in c.execute("SELECT * FROM listings ORDER BY unit_cents")]
    return [x for x in rows if (not category or category.lower() in x["category"].lower()) and (not q or q.lower() in (x["name"]+x["description"]).lower())]

@app.post("/api/procurement/parse")
def parse_request(body: ParseRequest):
    result=agent.run(body.mode, body.message, heuristic_parse, search_for)
    req=result["requirements"]
    if req.get("budget") is not None and float(req["budget"]) < 0: raise HTTPException(422,"Budget cannot be negative")
    advice=result.get("advice") or {}
    message=result.get("question") if result.get("needs_clarification") else (advice.get("summary") or recommendation_message(req, result["recommendations"]))
    return {**result,"ai_mode":req.get("source"),"ai_model":agent.llm_label(),"message":message}

def recommendation_message(req, options):
    if options:
        top=options[0]
        return f"I found {len(options)} catalogue option{'s' if len(options)!=1 else ''}. {top['name']} is the lowest-priced eligible match at ${top['line_total']} total. Compare the options, then add one to your draft."
    return "I couldn't find an in-stock catalogue match for all those constraints. Try a higher budget, a smaller quantity, or broader specifications."

@app.post("/api/orders")
def create_order(body: OrderRequest):
    order_id=str(uuid.uuid4())
    snap=[]; total=0
    with db() as c:
        for line in body.items:
            row=c.execute("SELECT * FROM listings WHERE id=?",(line.listing_id,)).fetchone()
            if not row: raise HTTPException(404,f"Unknown listing: {line.listing_id}")
            item=row_item(row)
            if line.quantity < item["min_qty"] or line.quantity > item["stock"]: raise HTTPException(409,f"{item['name']} is unavailable in quantity {line.quantity}")
            cents=int(row["unit_cents"])*line.quantity; total += cents
            snap.append({"listing_id":item["id"],"name":item["name"],"supplier":item["supplier"],"quantity":line.quantity,"unit_price":item["unit_price"],"line_total":f"{cents/100:.2f}"})
        created=datetime.now(timezone.utc).isoformat()
        c.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,?,?)",(order_id,body.mode,"awaiting_approval",CURRENCY,total,None,created,json.dumps(snap)))
    return {"id":order_id,"mode":body.mode,"status":"awaiting_approval","currency":CURRENCY,"total":f"{total/100:.2f}","items":snap,"created_at":created}

@app.get("/api/orders")
def list_orders():
    with db() as c: rows=c.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 30").fetchall()
    return [{"id":r["id"],"mode":r["mode"],"status":r["status"],"currency":r["currency"],"total":f"{r['total_cents']/100:.2f}","items":json.loads(r["items"]),"created_at":r["created_at"]} for r in rows]

def paypal_request(path, data=None, token=None):
    base=os.getenv("PAYPAL_BASE_URL","https://api-m.sandbox.paypal.com").rstrip("/")
    headers={"Content-Type":"application/json","Accept":"application/json"}
    if token: headers["Authorization"]="Bearer "+token
    req=urllib.request.Request(base+path,data=data,headers=headers,method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req,timeout=25) as res: return json.loads(res.read())
    except urllib.error.HTTPError as e:
        detail=e.read().decode("utf-8","replace")
        raise HTTPException(502,"PayPal request failed: "+detail[:500])

def paypal_token():
    cid=os.getenv("PAYPAL_CLIENT_ID"); secret=os.getenv("PAYPAL_CLIENT_SECRET")
    if not cid or not secret or cid.lower().startswith("your_") or secret.lower().startswith("your_"): raise HTTPException(503,"PayPal Sandbox is not configured. Add credentials to backend/.env.")
    url=os.getenv("PAYPAL_BASE_URL","https://api-m.sandbox.paypal.com").rstrip("/")+"/v1/oauth2/token"
    req=urllib.request.Request(url,data=urllib.parse.urlencode({"grant_type":"client_credentials"}).encode(),headers={"Authorization":"Basic "+__import__("base64").b64encode(f"{cid}:{secret}".encode()).decode(),"Content-Type":"application/x-www-form-urlencoded"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=20) as res: return json.loads(res.read())["access_token"]
    except urllib.error.HTTPError as e: raise HTTPException(502,"PayPal authentication failed: "+e.read().decode("utf-8","replace")[:400])

class PayRequest(BaseModel): order_id: str
class CaptureRequest(BaseModel): order_id: str; paypal_order_id: str

@app.post("/api/payments/create")
def create_paypal_order(body: PayRequest):
    with db() as c: order=c.execute("SELECT * FROM orders WHERE id=?",(body.order_id,)).fetchone()
    if not order: raise HTTPException(404,"Order not found")
    if order["status"] == "paid": raise HTTPException(409,"This order is already paid")
    token=paypal_token(); amount=f"{order['total_cents']/100:.2f}"
    result=paypal_request("/v2/checkout/orders",json.dumps({"intent":"CAPTURE","purchase_units":[{"reference_id":order["id"],"custom_id":order["id"],"amount":{"currency_code":order["currency"],"value":amount}}],"application_context":{"brand_name":"CartGenii","user_action":"PAY_NOW"}}).encode(),token)
    pid=result["id"]
    with db() as c:
        c.execute("UPDATE orders SET status='pending_payment',paypal_order_id=? WHERE id=?",(pid,order["id"]))
        c.execute("INSERT INTO payments VALUES(?,?,?,?,?,?,?,?)",(str(uuid.uuid4()),order["id"],pid,"created",order["total_cents"],order["currency"],datetime.now(timezone.utc).isoformat(),None))
    return {"paypal_order_id":pid,"status":result.get("status"),"client_id":os.getenv("PAYPAL_CLIENT_ID"),"currency":order["currency"]}

@app.post("/api/payments/capture")
def capture_paypal_order(body: CaptureRequest):
    with db() as c: order=c.execute("SELECT * FROM orders WHERE id=?",(body.order_id,)).fetchone()
    if not order: raise HTTPException(404,"Order not found")
    if order["status"] == "paid": return {"status":"paid","order_id":body.order_id,"message":"Payment was already verified."}
    if order["paypal_order_id"] != body.paypal_order_id: raise HTTPException(400,"PayPal order does not match this CartGenii order")
    token=paypal_token(); oid=urllib.parse.quote(body.paypal_order_id)
    try:
        result=paypal_request(f"/v2/checkout/orders/{oid}/capture",b"{}",token)
    except HTTPException as e:
        # Already captured (e.g. a retry after a dropped response): read the order back and verify it instead.
        if "ORDER_ALREADY_CAPTURED" not in str(e.detail): raise
        result=paypal_request(f"/v2/checkout/orders/{oid}",None,token)
    unit=(result.get("purchase_units") or [{}])[0]
    capture=(unit.get("payments",{}).get("captures") or [{}])[0]
    amount=capture.get("amount",{})
    # PayPal returns our custom_id on the capture (and sometimes on the purchase unit); reference_id is the same value.
    ref=capture.get("custom_id") or unit.get("custom_id") or unit.get("reference_id")
    checks={
        "order status COMPLETED": result.get("status")=="COMPLETED",
        "capture status COMPLETED": capture.get("status")=="COMPLETED",
        "currency matches": amount.get("currency_code")==order["currency"],
        "amount matches": dollars_to_cents(amount.get("value",0))==order["total_cents"],
        "order reference matches": ref==order["id"],
    }
    failed=[k for k,v in checks.items() if not v]
    if failed:
        print("PayPal capture NOT verified:", failed, "| order:", result.get("status"), "| capture:", capture.get("status"), capture.get("status_details"), "| amount:", amount, "| expected:", order["total_cents"], order["currency"])
        raise HTTPException(409,"PayPal capture was not verified: "+", ".join(failed))
    now=datetime.now(timezone.utc).isoformat()
    with db() as c:
        c.execute("UPDATE orders SET status='paid' WHERE id=?",(order["id"],))
        c.execute("UPDATE payments SET status='completed',captured_at=? WHERE order_id=? AND paypal_order_id=?",(now,order["id"],body.paypal_order_id))
    return {"status":"paid","order_id":order["id"],"capture_id":capture.get("id"),"amount":amount,"message":"Payment captured and verified by PayPal."}
