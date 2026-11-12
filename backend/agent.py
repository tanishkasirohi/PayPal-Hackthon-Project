"""CartGenii procurement agent.

The agent runs a fixed, auditable pipeline:

    1. understand  - LLM turns the buyer's words into a structured brief (or asks a follow-up question)
    2. search      - backend rules filter the catalogue (stock, MOQ, specs, budget)
    3. recover     - if nothing fits, backend rules relax one constraint at a time and report the gap
    4. rank        - backend scores options with documented, mode-specific weights
    5. advise      - LLM explains each option, names a pick and the trade-offs

The model never supplies product IDs, prices, stock, totals or payment status. Every ID the model
returns is checked against the options the backend found; anything else is discarded.
Works with any OpenAI-compatible Chat Completions API (OpenAI, Gemini, Groq, Anthropic, ...).
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from decimal import Decimal

# --------------------------------------------------------------------------- LLM client


def llm_configured() -> bool:
    key = os.getenv("LLM_API_KEY", "").strip()
    return bool(key) and not key.lower().startswith("your_")


def llm_label() -> str:
    return os.getenv("LLM_MODEL", "gpt-4o-mini") if llm_configured() else "demo parser"


def _extract_json(text: str):
    if not text:
        return None
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
    return None


def llm_json(system: str, user: str, timeout: int = 25):
    """Call the configured chat model and return a parsed JSON object, or None on any failure."""
    if not llm_configured():
        return None
    base = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    headers = {
        "Authorization": "Bearer " + os.getenv("LLM_API_KEY", "").strip(),
        "Content-Type": "application/json",
        "User-Agent": "CartGenii/1.1",
    }
    body = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system + "\nRespond with one JSON object only. No markdown."},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    for attempt in range(2):
        req = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                data = json.loads(res.read())
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, list):  # some providers return content parts
                content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
            parsed = _extract_json(content)
            return parsed if isinstance(parsed, dict) else None
        except urllib.error.HTTPError as e:
            # Some providers reject response_format; retry once without it.
            if attempt == 0 and e.code in (400, 422):
                body.pop("response_format", None)
                continue
            print("LLM HTTP error", e.code, e.read()[:300])
            return None
        except Exception as e:  # timeout, bad JSON, network
            print("LLM error", repr(e)[:300])
            return None
    return None


# --------------------------------------------------------------------------- 1. understand

UNDERSTAND_PROMPT = """You are the intake step of CartGenii, a procurement assistant.
Convert the buyer's request into a structured brief. Mode is "{mode}" ({mode_hint}).
Catalogue categories: Electronics (laptops, monitors, headphones), Apparel (t-shirts), Stationery (notebooks, pens).
Known attribute keys: ram_gb, storage_gb, display_in, use, colour, material, sizes (list like ["S","M","L","XL"]), size, pages, type, pack_size.
Return JSON with keys:
  category: "electronics" | "apparel" | "stationery"
  product_query: short noun such as "laptop", "t-shirt", "notebook", "pen", "monitor", "headphones"
  quantity: integer or null if the buyer did not say
  budget: total budget as a number or null (convert "under $900" to 900; for business a total budget)
  specifications: object using only the known attribute keys; numbers for numeric minimums; expand ranges like "S to XL" to ["S","M","L","XL"]
  priorities: list of what matters most to the buyer, e.g. ["price","performance","portability","eco-friendly","fast delivery"]
  missing: list of essential fields the buyer did not give (business mode: quantity is essential; budget is optional)
  clarifying_question: one short, friendly question that would fill the most important missing field, or null
Never invent products, prices or stock."""


def understand(mode: str, message: str, fallback):
    parsed = llm_json(
        UNDERSTAND_PROMPT.format(
            mode=mode,
            mode_hint="one buyer, usually one item" if mode == "individual" else "a business buying in bulk from suppliers",
        ),
        message,
    )
    if not parsed:
        req = fallback(mode, message)
        req["source"] = "demo parser"
        req["priorities"] = ["price"]
        req["missing"], req["clarifying_question"] = [], None
        bare = re.sub(r"\$\s*\d[\d,]*(?:\.\d+)?", "", message)
        if mode == "business" and not re.search(r"\b\d{1,5}\b", bare):
            req["quantity"] = None
            req["missing"] = ["quantity"]
            req["clarifying_question"] = "How many units do you need?"
        return req
    req = {"mode": mode, "currency": os.getenv("APP_CURRENCY", "USD").upper(), "source": "AI model"}
    req["category"] = str(parsed.get("category") or "").lower() or None
    req["product_query"] = str(parsed.get("product_query") or "").lower() or None
    try:
        qty = parsed.get("quantity")
        req["quantity"] = max(1, min(10000, int(qty))) if qty not in (None, "") else None
    except (TypeError, ValueError):
        req["quantity"] = None
    try:
        budget = parsed.get("budget")
        req["budget"] = float(budget) if budget not in (None, "") and float(budget) > 0 else None
    except (TypeError, ValueError):
        req["budget"] = None
    specs = parsed.get("specifications")
    req["specifications"] = specs if isinstance(specs, dict) else {}
    pr = parsed.get("priorities")
    req["priorities"] = [str(p) for p in pr][:4] if isinstance(pr, list) else []
    missing = parsed.get("missing")
    req["missing"] = [str(m) for m in missing] if isinstance(missing, list) else []
    q = parsed.get("clarifying_question")
    req["clarifying_question"] = str(q) if q else None
    # Only block on a genuinely essential gap (business quantity); otherwise fill sensible defaults.
    if req["quantity"] is None and mode == "individual":
        req["quantity"] = 1
    if req["quantity"]:
        req["clarifying_question"] = None
    elif not req["clarifying_question"]:
        req["clarifying_question"] = "How many units do you need?"
    return req


# --------------------------------------------------------------------------- 3. recover


def find_alternatives(req, search):
    """Relax one constraint at a time with backend rules and report what had to give."""
    alts = []
    seen = set()

    def add(options, note, limit=3):
        for o in options[:limit]:
            if o["id"] in seen:
                continue
            seen.add(o["id"])
            o["relaxation"] = note
            alts.append(o)

    if req.get("budget") is not None:
        no_budget = dict(req, budget=None)
        budget = Decimal(str(req["budget"]))
        for o in search(no_budget)[:3]:
            gap = Decimal(o["line_total"]) - budget
            add([o], f"Over budget by ${gap:.2f}" if gap > 0 else "Fits budget")
    for key in list((req.get("specifications") or {}).keys()):
        relaxed = dict(req, specifications={k: v for k, v in req["specifications"].items() if k != key})
        add(search(relaxed), f"Doesn't meet: {key.replace('_', ' ')}", 2)
    qty = int(req.get("quantity") or 1)
    if qty > 1:
        for q in (qty // 2, max(1, qty // 4)):
            opts = search(dict(req, quantity=q))
            if opts:
                add(opts, f"Only {q} units available within your constraints", 2)
                break
    return alts[:6]


# --------------------------------------------------------------------------- 4. rank

RANKING_RULES = {
    "individual": "60% price (cheaper scores higher) + 40% spec headroom above your minimums",
    "business": "70% unit cost (cheaper scores higher) + 30% stock buffer above your quantity",
}


def rank(req, options):
    if not options:
        return options
    totals = [Decimal(o["line_total"]) for o in options]
    lo, hi = min(totals), max(totals)
    specs = req.get("specifications") or {}
    qty = int(req.get("quantity") or 1)
    for o in options:
        t = Decimal(o["line_total"])
        price_score = Decimal(1) if hi == lo else (hi - t) / (hi - lo)
        if req.get("mode") == "business":
            buffer = min(Decimal(o["stock"]) / Decimal(max(qty, 1)), Decimal(3)) / Decimal(3)
            score = Decimal("0.7") * price_score + Decimal("0.3") * buffer
        else:
            headroom = []
            for k, v in specs.items():
                av = o["attributes"].get(k)
                if isinstance(v, (int, float)) and isinstance(av, (int, float)) and v > 0:
                    headroom.append(min(Decimal(str(av)) / Decimal(str(v)), Decimal(2)) - 1)
            spec_score = sum(headroom) / len(headroom) if headroom else Decimal("0.5")
            score = Decimal("0.6") * price_score + Decimal("0.4") * spec_score
        o["score"] = int((score * 100).quantize(Decimal("1")))
    options.sort(key=lambda o: (-o["score"], Decimal(o["line_total"])))
    return options


# --------------------------------------------------------------------------- 5. advise

ADVISE_PROMPT = """You are the procurement advisor in CartGenii. Mode: {mode}.
You get the buyer's request, their structured brief and the ONLY options that exist (already filtered and
scored by the backend). Explain them like a sharp, honest purchasing assistant.
Rules: use only the given option ids, prices and facts; never invent products, discounts, delivery dates or stock.
Return JSON with keys:
  summary: 2 sentences answering the buyer directly (mention the pick and the key reason)
  recommended_id: id of the single best option for this buyer's priorities
  options: list of {{"id": ..., "why": one sentence on fit, "tradeoff": one short sentence on the downside}}
  tip: one practical procurement tip for this purchase, or null"""


def advise(req, options, message, alternatives=None):
    pool = options or alternatives or []
    facts = [
        {
            "id": o["id"], "name": o["name"], "supplier": o["supplier"], "unit_price": o["unit_price"],
            "quantity": o["quantity"], "line_total": o["line_total"], "stock": o["stock"], "min_qty": o["min_qty"],
            "attributes": o["attributes"], "backend_score": o.get("score"), "relaxation": o.get("relaxation"),
        }
        for o in pool[:6]
    ]
    result = None
    if facts:
        brief = {k: req.get(k) for k in ("category", "product_query", "quantity", "budget", "specifications", "priorities")}
        user = json.dumps({"request": message, "brief": brief, "exact_matches": bool(options), "options": facts})
        result = llm_json(ADVISE_PROMPT.format(mode=req.get("mode")), user)
    valid_ids = {f["id"] for f in facts}
    notes = {}
    if result:
        for item in result.get("options") or []:
            if isinstance(item, dict) and item.get("id") in valid_ids:
                notes[item["id"]] = {"why": str(item.get("why") or ""), "tradeoff": str(item.get("tradeoff") or "")}
        rec = result.get("recommended_id") if result.get("recommended_id") in valid_ids else None
        return {
            "summary": str(result.get("summary") or ""),
            "recommended_id": rec or (facts[0]["id"] if facts else None),
            "notes": notes,
            "tip": result.get("tip"),
            "source": "AI model",
        }
    # Deterministic fallback explanation
    if options:
        top = options[0]
        summary = (f"{top['name']} from {top['supplier']} is the best fit at ${top['line_total']} "
                   f"for {top['quantity']} unit{'s' if top['quantity'] != 1 else ''}. "
                   f"{len(options)} option{'s' if len(options) != 1 else ''} meet all your requirements.")
        for o in options:
            notes[o["id"]] = {"why": "Meets every requirement.", "tradeoff": ""}
        return {"summary": summary, "recommended_id": top["id"], "notes": notes, "tip": None, "source": "backend rules"}
    if alternatives:
        return {"summary": "Nothing meets every requirement, so here are the closest options and what each one misses.",
                "recommended_id": None, "notes": {}, "tip": None, "source": "backend rules"}
    return {"summary": "Nothing in the catalogue matches this request. Try a different product or broader specifications.",
            "recommended_id": None, "notes": {}, "tip": None, "source": "backend rules"}


# --------------------------------------------------------------------------- orchestration


def run(mode: str, message: str, fallback_parser, search):
    trace = []

    def step(name, actor, detail, t0):
        trace.append({"step": name, "actor": actor, "detail": detail, "ms": int((time.time() - t0) * 1000)})

    t0 = time.time()
    req = understand(mode, message, fallback_parser)
    bits = [req.get("product_query") or req.get("category") or "item"]
    if req.get("quantity"):
        bits.append(f"qty {req['quantity']}")
    if req.get("budget"):
        bits.append(f"budget ${req['budget']:g}")
    bits += [f"{k.replace('_', ' ')} {v if not isinstance(v, list) else '/'.join(map(str, v))}" for k, v in (req.get("specifications") or {}).items()]
    step("Understand request", req["source"], ", ".join(bits), t0)

    if req.get("clarifying_question") and not req.get("quantity"):
        return {"requirements": req, "needs_clarification": True, "question": req["clarifying_question"],
                "recommendations": [], "alternatives": [], "advice": None, "trace": trace}

    t0 = time.time()
    options = search(req)
    step("Search catalogue", "backend rules", f"{len(options)} listing{'s' if len(options) != 1 else ''} pass stock, MOQ, spec and budget checks", t0)

    alternatives = []
    if not options:
        t0 = time.time()
        alternatives = find_alternatives(req, search)
        step("Find closest alternatives", "backend rules", f"{len(alternatives)} near-miss option{'s' if len(alternatives) != 1 else ''}", t0)

    t0 = time.time()
    rank(req, options)
    rank(req, alternatives)
    step("Rank options", "backend rules", RANKING_RULES.get(mode, ""), t0)

    t0 = time.time()
    advice = advise(req, options, message, alternatives)
    step("Explain & recommend", advice["source"], "pick + trade-offs for each option", t0)

    for o in options + alternatives:
        note = advice["notes"].get(o["id"])
        if note:
            o["why"], o["tradeoff"] = note["why"], note["tradeoff"]
        o["recommended"] = o["id"] == advice.get("recommended_id")
    return {"requirements": req, "needs_clarification": False, "recommendations": options,
            "alternatives": alternatives, "advice": advice, "trace": trace}
