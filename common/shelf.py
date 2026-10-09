"""Turns raw retailer search results from Nimble into one row shape for every retailer."""
import re
from datetime import datetime, timezone

RETAILERS = {
    # retailer: (Extraction Template, name of its search parameter)
    "amazon": ("amazon_serp", "keyword"),
    "walmart": ("walmart_serp", "keyword"),
    "target": ("target_serp", "keyword"),
    "footlocker": ("footlocker_serp", "keywords"),
    "asos": ("asos_serp", "keyword"),
}

BRANDS = [
    ("Jordan", r"\bjordan\b"), ("Nike", r"\bnike\b"), ("adidas", r"\badidas\b"), ("HOKA", r"\bhoka\b"),
    ("New Balance", r"\bnew balance\b|^new-balance"), ("Asics", r"\basics\b"), ("Brooks", r"\bbrooks\b"),
    ("Saucony", r"\bsaucony\b"), ("Puma", r"\bpuma\b"), ("Under Armour", r"\bunder armour\b|^under-armour"),
    ("Reebok", r"\breebok\b"), ("Skechers", r"\bskechers\b"), ("Mizuno", r"\bmizuno\b"),
    ("Salomon", r"\bsalomon\b"), ("On", r"\bon cloud|\bon running\b|^on-|^on$"),
]


def _first(item, *keys):
    for k in keys:
        v = item.get(k)
        if v not in (None, "", []):
            return v
    return None


def _num(v, integer=False):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v) if integer else float(v)
    s = re.sub(r"[^0-9.]", "", str(v))
    if not s or s == ".":
        return None
    try:
        return int(float(s)) if integer else float(s)
    except ValueError:
        return None


def _bool(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    return str(v).strip().lower() in ("true", "1", "yes")


def brand_of(name, given, url):
    text = (name or "").lower()
    slug = ""
    m = re.search(r"amazon\.com/([^/]+)/dp/", url or "")
    if m:
        slug = m.group(1).lower()
    given_text = (given or "").strip().lower()
    for brand, pattern in BRANDS:
        if re.search(pattern, text) or re.search(pattern, given_text) or (slug and re.search(pattern, slug.replace("-", " "))):
            return brand
    if given and given.strip().lower() not in ("men's", "mens", "women's", "womens", "unisex", "kids"):
        return given.strip()
    return None


def normalise(retailer, keyword, item, captured_at=None):
    name = _first(item, "product_name", "title")
    url = _first(item, "product_url", "url")
    pid = _first(item, "asin", "tcin", "product_id")
    if not url and retailer == "footlocker" and pid:
        url = f"https://www.footlocker.com/product/~/{pid}.html"
    price = _num(_first(item, "price", "product_price", "price_current"))
    list_price = _num(_first(item, "original_price", "product_price_original", "list_price"))
    if list_price is not None and price is not None and list_price <= price:
        list_price = None
    in_stock = None
    if retailer == "walmart" and "product_out_of_stock" in item:
        in_stock = not _bool(item.get("product_out_of_stock"))
    elif retailer == "target" and item.get("availability"):
        in_stock = str(item.get("availability")).upper() == "IN_STOCK"
    return {
        "retailer": retailer,
        "search_keyword": keyword,
        "position": _num(_first(item, "position", "item_stack_position"), integer=True),
        "product_name": name,
        "brand": brand_of(name, _first(item, "product_brand", "brand"), url),
        "price": price,
        "list_price": list_price,
        "discount_pct": round(100 * (list_price - price) / list_price, 1) if list_price and price else None,
        "rating": _num(_first(item, "rating", "product_rating")),
        "review_count": _num(_first(item, "review_count", "product_reviews_count"), integer=True),
        "sponsored": _bool(_first(item, "sponsored", "is_sponsored", "is_promotion")),
        "in_stock": in_stock,
        "product_id": str(pid) if pid is not None else None,
        "product_url": url,
        "image_url": _first(item, "image_url", "product_image"),
        "captured_at": captured_at or datetime.now(timezone.utc),
    }
