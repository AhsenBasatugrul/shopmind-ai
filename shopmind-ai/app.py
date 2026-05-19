"""ShopMind AI — production-grade Flask app with professional scraping."""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import secrets
import tempfile
import time
from datetime import datetime
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from google import genai as google_genai
from google.genai import types as genai_types

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyCn_n1W52G9ao_NEwkjUdeAmAhGw8vtB2k")
_genai_client = google_genai.Client(api_key=GEMINI_API_KEY)
_GEMINI_MODEL = "gemini-2.5-flash"

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "shopmind-ai-secret-key-2024")

USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")
_ANALYSIS_DIR = os.path.join(tempfile.gettempdir(), "shopmind_analyses")
os.makedirs(_ANALYSIS_DIR, exist_ok=True)

LANG_PROMPTS = {
    "tr": "Tüm metin içeriklerini (özet, özellikler, hedef kitle vb.) Türkçe yaz.",
    "en": "Write all text content (summary, features, audiences, etc.) in English.",
    "de": "Schreibe alle Texte (Zusammenfassung, Merkmale, Zielgruppen usw.) auf Deutsch.",
    "fr": "Écris tous les textes (résumé, caractéristiques, publics cibles, etc.) en français.",
    "es": "Escribe todo el contenido (resumen, características, audiencias, etc.) en español.",
    "ar": "اكتب جميع النصوص (الملخص والميزات والفئات المستهدفة وما إلى ذلك) باللغة العربية.",
    "ru": "Пиши весь текстовый контент (резюме, характеристики, целевую аудиторию и т.д.) на русском языке.",
    "zh": "用中文写所有文本内容（摘要、特点、目标受众等）。",
}

# ---------------------------------------------------------------------------
# Browser fingerprints & bot signals
# ---------------------------------------------------------------------------

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

_HOME_URLS: dict[str, str] = {
    "hepsiburada": "https://www.hepsiburada.com",
    "amazon": "https://www.amazon.com.tr",
    "trendyol": "https://www.trendyol.com",
}

# Strong signals → bot page regardless of size
_BOT_STRONG = frozenset([
    "cloudflare", "just a moment", "ddos-guard", "cf-ray",
    "checking your browser", "enable javascript and cookies",
    "browser integrity check", "security check to access",
    "_cf_chl", "challenge-form", "cf_clearance",
])
# Weak signals → only flag when page is small (<25KB)
_BOT_WEAK = frozenset([
    "validatecaptcha", "captchacharacters", "robot check",
    "automated access", "verify you are human", "not a robot",
    "unusual traffic", "automated queries", "access denied",
    "doğrulama", "güvenlik kontrolü", "erişim engellendi",
])

_IMG_EXTS = frozenset([".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"])
_CDN_HINTS = frozenset(["cdn.", "images.", "productimages.", "img.", "static.", "media.", "assets."])

# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------

def _make_headers(ua: str | None = None) -> dict:
    ua = ua or random.choice(_USER_AGENTS)
    chrome_v = next((v for v in ("124", "123", "122") if v in ua), "124")
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "sec-ch-ua": f'"Google Chrome";v="{chrome_v}", "Chromium";v="{chrome_v}", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }


def _make_api_headers(origin: str = "") -> dict:
    h = _make_headers()
    h.update({
        "Accept": "application/json, text/plain, */*",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "X-Requested-With": "XMLHttpRequest",
    })
    if origin:
        h["Origin"] = origin
        h["Referer"] = origin.rstrip("/") + "/"
    return h


def _create_session(site: str | None = None) -> requests.Session:
    """Build a requests.Session, optionally pre-warming with site homepage for cookies."""
    sess = requests.Session()
    sess.headers.update(_make_headers())
    if site and site in _HOME_URLS:
        try:
            sess.get(_HOME_URLS[site], timeout=8, allow_redirects=True)
            time.sleep(random.uniform(0.3, 0.8))
        except Exception:
            pass
    return sess


def _get(url: str, sess: requests.Session, *, retries: int = 2, timeout: int = 15) -> requests.Response | None:
    """GET with exponential backoff on transient 4xx/5xx and network errors."""
    for attempt in range(retries + 1):
        try:
            resp = sess.get(url, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
            return resp
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else 0
            if code in (403, 429, 503) and attempt < retries:
                time.sleep(2 ** attempt + random.uniform(0, 1))
                continue
            return None
        except (requests.ConnectionError, requests.Timeout):
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            return None
        except Exception:
            return None
    return None


def _is_bot_page(html: str) -> bool:
    lower = html.lower()
    if any(s in lower for s in _BOT_STRONG):
        return True
    return len(html) < 25000 and any(s in lower for s in _BOT_WEAK)

# ---------------------------------------------------------------------------
# Playwright fallback (optional — only used when HTML parsing fails)
# ---------------------------------------------------------------------------

def _render_playwright(url: str) -> str | None:
    """Render page via headless Chromium. Returns HTML or None if unavailable."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=random.choice(_USER_AGENTS),
                locale="tr-TR",
                viewport={"width": 1280, "height": 800},
            )
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)
            html = page.content()
            browser.close()
            print(f"[Playwright OK] {url[:70]}")
            return html
    except ImportError:
        return None
    except Exception as e:
        print(f"[Playwright error] {e}")
        return None

# ---------------------------------------------------------------------------
# Scalar helpers
# ---------------------------------------------------------------------------

def _sf(val, default: float = 0.0) -> float:
    try:
        return float(str(val).replace(",", "."))
    except Exception:
        return default


def _si(val, default: int = 0) -> int:
    try:
        return int(str(val).replace(".", "").replace(",", ""))
    except Exception:
        return default


def _s(val) -> str:
    if not val:
        return ""
    if isinstance(val, list):
        return " ".join(str(v) for v in val if v)
    return str(val).strip()


def _parse_rating(text: str) -> float:
    m = re.search(r"\d+[,.]\d+|\d+", str(text or ""))
    if not m:
        return 0.0
    v = _sf(m.group())
    return v if v <= 5 else v / 10.0


def _parse_count(text: str) -> int:
    m = re.search(r"\d[\d.,]*", str(text or ""))
    return _si(m.group()) if m else 0


def _fmt_price(val) -> str:
    if not val:
        return ""
    if isinstance(val, (int, float)):
        return f"₺{val:,.0f}".replace(",", ".")
    s = str(val).strip()
    return s if any(c in s for c in "₺$€£") else f"₺{s}"


def _abs_url(src: str, base: str) -> str:
    if not src:
        return ""
    src = src.strip()
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        p = urlparse(base)
        return f"{p.scheme}://{p.netloc}{src}"
    return src


def _valid_img(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    p = urlparse(url)
    return (
        any(p.path.lower().endswith(e) for e in _IMG_EXTS)
        or any(h in p.netloc.lower() for h in _CDN_HINTS)
    )


def _coerce_img(val) -> str:
    if not val:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, list) and val:
        first = val[0]
        return first if isinstance(first, str) else (
            first.get("url") or first.get("src") or "" if isinstance(first, dict) else ""
        )
    if isinstance(val, dict):
        return val.get("url") or val.get("src") or ""
    return ""


def _coerce_cat(val) -> str:
    if isinstance(val, dict):
        return val.get("name") or val.get("categoryName") or ""
    if isinstance(val, list) and val:
        return str(val[-1]) if isinstance(val[-1], str) else ""
    return _s(val)

# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _text(soup: BeautifulSoup, *selectors: str) -> str:
    """Return text of first matching selector."""
    for sel in selectors:
        try:
            el = soup.select_one(sel)
            if el:
                t = el.get_text(strip=True)
                if t:
                    return t
        except Exception:
            pass
    return ""


def _og_image(soup: BeautifulSoup) -> str:
    for attrs in [{"property": "og:image"}, {"property": "og:image:secure_url"}, {"name": "twitter:image"}]:
        el = soup.find("meta", attrs=attrs)
        if el and el.get("content"):
            return el["content"]
    link = soup.find("link", rel="preload", attrs={"as": "image"})
    return link["href"] if link and link.get("href") else ""


def _meta_desc(soup: BeautifulSoup) -> str:
    for attr, name in [("property", "og:description"), ("name", "description"), ("name", "twitter:description")]:
        el = soup.select_one(f'meta[{attr}="{name}"]')
        if el and el.get("content"):
            return el["content"][:400]
    return ""


def _json_ld(soup: BeautifulSoup) -> dict:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
            if isinstance(data, list):
                data = next(
                    (d for d in data if isinstance(d, dict) and d.get("@type") in ("Product", "ItemPage")),
                    data[0] if data else {},
                )
            if isinstance(data, dict) and data.get("@type") in ("Product", "ItemPage", "WebPage"):
                return data
        except Exception:
            pass
    return {}


def _window_prop(html: str, key: str) -> dict:
    """Extract window[key] = {...} JSON from raw HTML."""
    for marker in (f'window["{key}"]', f"window['{key}']", f"window.{key}"):
        idx = html.find(marker)
        if idx == -1:
            continue
        start = html.find("{", idx)
        if start == -1:
            continue
        raw = html[start:]
        depth = end = 0
        for i, ch in enumerate(raw):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        try:
            return json.loads(raw[:end]) if end else {}
        except Exception:
            return {}
    return {}


def _deep_find(data, *keys: str, depth: int = 6) -> dict | None:
    """Recursively search for the first dict that contains any of the given keys."""
    if depth == 0 or not data:
        return None
    if isinstance(data, dict):
        if any(k in data for k in keys):
            return data
        for v in data.values():
            r = _deep_find(v, *keys, depth=depth - 1)
            if r:
                return r
    elif isinstance(data, list):
        for item in data[:30]:
            r = _deep_find(item, *keys, depth=depth - 1)
            if r:
                return r
    return None

# ---------------------------------------------------------------------------
# Product normalization
# ---------------------------------------------------------------------------

def _normalize(raw: dict, base_url: str = "") -> dict:
    """Normalize any raw product dict into the standard schema."""
    name = _s(raw.get("name") or raw.get("productName") or raw.get("title") or "")

    brand = raw.get("brand") or raw.get("brandName") or ""
    if isinstance(brand, dict):
        brand = brand.get("name") or ""
    brand = _s(brand)

    # Price — handles dict, scalar, or formatted string
    price_raw = (raw.get("price") or raw.get("salePrice") or raw.get("listPrice")
                 or raw.get("priceInfo") or raw.get("priceValue") or 0)
    if isinstance(price_raw, dict):
        formatted = price_raw.get("formattedPrice") or price_raw.get("formattedPriceValue") or ""
        price_raw = formatted or price_raw.get("priceValue") or price_raw.get("value") or 0
    price = _fmt_price(price_raw) if price_raw else ""

    # Rating
    rating_raw = (raw.get("rating") or raw.get("aggregateRating")
                  or raw.get("ratingInfo") or raw.get("ratingScore") or {})
    if isinstance(rating_raw, dict):
        rating = _sf(rating_raw.get("ratingValue") or rating_raw.get("averageRating") or rating_raw.get("score"))
        review_count = _si(rating_raw.get("reviewCount") or rating_raw.get("totalCount") or rating_raw.get("commentCount"))
    else:
        rating = _sf(rating_raw)
        review_count = 0
    if not rating:
        rating = _sf(raw.get("averageRating") or raw.get("ratingValue"))
    if not review_count:
        review_count = _si(raw.get("reviewCount") or raw.get("totalCount")
                           or raw.get("commentCount") or raw.get("review_count"))

    # Image
    image = _coerce_img(
        raw.get("images") or raw.get("photoUrls") or raw.get("image")
        or raw.get("coverImage") or raw.get("mainImage") or ""
    )
    if image and base_url and not image.startswith("http"):
        image = _abs_url(image, base_url)

    category = _coerce_cat(raw.get("category") or raw.get("categoryName") or "")
    description = _s(raw.get("description") or raw.get("shortDescription") or raw.get("productDescription") or "")[:600]

    return dict(
        name=name, brand=brand, price=price, rating=rating,
        image=image, category=category, review_count=review_count,
        reviews=[], description=description,
    )


def _has_data(p: dict) -> bool:
    name = (p.get("name") or "").strip()
    return bool(name and name not in ("", "Ürün", "Product", "undefined", "null", "None") and len(name) > 3)

# ---------------------------------------------------------------------------
# Site detection
# ---------------------------------------------------------------------------

def _detect_site(url: str) -> str:
    u = url.lower()
    if "trendyol.com" in u:
        return "trendyol"
    if "hepsiburada.com" in u:
        return "hepsiburada"
    if "amazon.com" in u:
        return "amazon"
    if "n11.com" in u:
        return "n11"
    return "generic"


def _name_from_url(url: str) -> str:
    path = unquote(urlparse(url).path.strip("/"))
    u = url.lower()
    if "hepsiburada.com" in u:
        m = re.match(r"(.+?)-pm-[A-Za-z0-9]+$", path)
        slug = m.group(1) if m else path.split("/")[-1]
    elif "trendyol.com" in u:
        last = path.split("/")[-1]
        m = re.match(r"(.+)-p-\d+", last)
        slug = m.group(1) if m else last
    elif "amazon.com" in u:
        parts = path.split("/")
        slug = parts[-3] if "dp" in parts and parts.index("dp") >= 2 else parts[-1]
    else:
        slug = path.split("/")[-1]
    name = re.sub(r"[-_]+", " ", re.sub(r"-pm-.*", "", slug)).strip()
    return " ".join(w.capitalize() for w in name.split() if w)

# ===========================================================================
# TRENDYOL extractor
# ===========================================================================

def _ty_ids(url: str) -> tuple[str, str]:
    qs = parse_qs(urlparse(url).query)
    pid = qs.get("contentId", [None])[0]
    if not pid:
        m = re.search(r"-p-(\d+)", urlparse(url).path)
        pid = m.group(1) if m else ""
    mid = qs.get("merchantId", [""])[0]
    return pid, mid


def _ty_reviews(pid: str, max_reviews: int = 200) -> list[str]:
    reviews: list[str] = []
    last_id = 0
    headers = _make_api_headers("https://www.trendyol.com")
    for _ in range(10):
        try:
            resp = requests.get(
                "https://public.trendyol.com/discovery-web-social-gw-service/api/getRatingAndReviewsByProductId",
                params={"productId": pid, "variantId": "", "lastRatingId": last_id,
                        "channel": "WEB", "channelId": "1", "merchantId": ""},
                headers=headers, timeout=10,
            )
            result = resp.json().get("result", {})
            batch = result.get("ratingAndReviews", [])
            if not batch:
                break
            for item in batch:
                t = _s(item.get("comment") or item.get("reviewText") or "")
                if t and len(t) > 5:
                    reviews.append(t)
            last_id = result.get("lastRatingId", 0)
            if not last_id or len(reviews) >= max_reviews:
                break
            time.sleep(0.2)
        except Exception as e:
            print(f"[Trendyol reviews error] {e}")
            break
    print(f"[Trendyol] {len(reviews)} yorum")
    return reviews


def _ty_extract(url: str, soup: BeautifulSoup | None) -> dict | None:
    pid, mid = _ty_ids(url)

    # 1. Public API (primary path — no bot protection)
    if pid:
        try:
            resp = requests.get(
                "https://public.trendyol.com/discovery-web-productgw-service/api/renderwidget/product-detail",
                params={"channelId": "1", "merchantId": mid, "contentId": pid},
                headers=_make_api_headers("https://www.trendyol.com"), timeout=12,
            )
            prod = resp.json().get("result", {}).get("product", {})
            if prod and prod.get("name"):
                p = _normalize(prod, url)
                # Ensure CDN image has full URL
                if not p["image"]:
                    imgs = prod.get("images", [])
                    if imgs:
                        raw_img = imgs[0] if isinstance(imgs[0], str) else imgs[0].get("url", "")
                        p["image"] = raw_img if raw_img.startswith("http") else f"https://cdn.dsmcdn.com/{raw_img}"
                elif not p["image"].startswith("http"):
                    p["image"] = f"https://cdn.dsmcdn.com/{p['image']}"
                # Rating fields from ratingScore sub-object
                if not p["rating"]:
                    rs = prod.get("ratingScore", {}) if isinstance(prod.get("ratingScore"), dict) else {}
                    p["rating"] = _sf(rs.get("averageRating"))
                    p["review_count"] = _si(rs.get("totalCount") or rs.get("commentCount"))
                p["reviews"] = _ty_reviews(pid)
                print(f"[Trendyol API OK] {p['name']}")
                return p
        except Exception as e:
            print(f"[Trendyol API error] {e}")

    if not soup:
        return None

    # 2. Embedded window state
    raw_html = str(soup)
    shared = _window_prop(raw_html, "__envoy__SHARED_PROPS")
    prod = shared.get("product", {})
    ld = _json_ld(soup)

    name = prod.get("name") or ld.get("name") or _text(soup, 'h1[class*="pr-new-br"]', "h1")
    brand_raw = prod.get("brand", {})
    brand = (brand_raw.get("name") if isinstance(brand_raw, dict) else _s(brand_raw)) or \
            (ld.get("brand", {}).get("name") if isinstance(ld.get("brand"), dict) else "") or \
            _text(soup, '[class*="brand"]')
    rs = prod.get("ratingScore", {}) if isinstance(prod.get("ratingScore"), dict) else {}
    rating = _sf(rs.get("averageRating"))
    review_count = _si(rs.get("totalCount") or rs.get("commentCount"))
    og = soup.find("meta", attrs={"property": "product:price:amount"})
    price = f"₺{og['content']}" if og and og.get("content") else ""
    if not price:
        ld_off = ld.get("offers", {})
        if isinstance(ld_off, list):
            ld_off = ld_off[0] if ld_off else {}
        if ld_off.get("price"):
            price = f"₺{ld_off['price']}"
    image = _og_image(soup)
    if not image:
        pl = soup.find("link", rel="preload", attrs={"as": "image"})
        image = pl["href"] if pl and pl.get("href") else ""
    cat_raw = prod.get("category", {})
    category = cat_raw.get("name") if isinstance(cat_raw, dict) else _coerce_cat(cat_raw)
    description = _text(soup, '[class*="product-description"]', '[class*="detail-desc"]')[:600]
    reviews = [el.get_text(strip=True) for el in
               soup.select('.comment-text, [class*="rnr-com-tx"]') if len(el.get_text(strip=True)) > 15]
    if pid and not reviews:
        reviews = _ty_reviews(pid)

    return dict(name=name, brand=brand, price=price, rating=rating, image=image,
                category=category, review_count=review_count, reviews=reviews, description=description)

# ===========================================================================
# HEPSIBURADA extractor
# ===========================================================================

def _hb_sku(url: str) -> str | None:
    m = re.search(r"-pm-([A-Za-z0-9]+)", urlparse(url).path)
    return m.group(1) if m else None


def _hb_api(sku: str) -> dict | None:
    """Try HB internal REST API endpoints — less bot-protected than HTML."""
    headers = _make_api_headers("https://www.hepsiburada.com")
    endpoints = [
        f"https://www.hepsiburada.com/api/product/listing/getbyproductcode/listing?productCode={sku}",
        f"https://www.hepsiburada.com/api/product/detail?productGroupId={sku}",
        f"https://www.hepsiburada.com/listing/api/navigation/product?productGroupId={sku}",
    ]
    for ep in endpoints:
        try:
            resp = requests.get(ep, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue
            raw = resp.json()
            items = raw.get("products") or raw.get("result") or raw.get("data") or []
            if isinstance(items, dict):
                items = [items]
            prod = (items[0] if isinstance(items, list) and items else None) or (
                raw if (raw.get("name") or raw.get("productName")) else None
            )
            if prod:
                result = _normalize(prod)
                if result["name"]:
                    print(f"[HB API OK] {result['name']}")
                    return result
        except Exception as e:
            print(f"[HB API error] {ep[:60]} → {e}")
    return None


def _hb_embedded(soup: BeautifulSoup) -> dict | None:
    """Extract product data from HB embedded JS state (Next.js, window props, hydration)."""

    # 1. __NEXT_DATA__ — recursive deep search first, then explicit paths
    next_el = soup.find("script", id="__NEXT_DATA__")
    if next_el and next_el.string:
        try:
            nd = json.loads(next_el.string)
            # Recursive search for any dict with product name fields
            prod = _deep_find(nd, "name", "productName", depth=7)
            if prod and (prod.get("name") or prod.get("productName")):
                result = _normalize(prod)
                if result["name"]:
                    print(f"[HB NEXT_DATA deep OK] {result['name']}")
                    return result
            # Explicit path traversal in pageProps
            page_props = nd.get("props", {}).get("pageProps", {})
            for path in (
                ["product"], ["productDetail"], ["productGroup"],
                ["initialData", "product"], ["data", "product"], ["listing", "product"],
            ):
                obj = page_props
                for k in path:
                    obj = obj.get(k) if isinstance(obj, dict) else None
                if isinstance(obj, dict) and (obj.get("name") or obj.get("productName")):
                    result = _normalize(obj)
                    if result["name"]:
                        print(f"[HB NEXT_DATA path OK] {result['name']}")
                        return result
        except Exception as e:
            print(f"[HB __NEXT_DATA__ error] {e}")

    # 2. window.* properties
    raw_html = str(soup)
    for key in ("__PRODUCT_DETAIL_APP_INITIAL_STATE__", "__INITIAL_STATE__", "__APP_INITIAL_STATE__"):
        state = _window_prop(raw_html, key)
        if not state:
            continue
        prod = state.get("product") or state.get("productDetail") or {}
        if not prod and (state.get("name") or state.get("productName")):
            prod = state
        if prod and (prod.get("name") or prod.get("productName")):
            result = _normalize(prod)
            if result["name"]:
                print(f"[HB window.{key} OK] {result['name']}")
                return result

    # 3. RSC / Next.js hydration chunks (self.__next_f.push)
    for script in soup.find_all("script"):
        text = script.string or ""
        if "__next_f.push" not in text:
            continue
        m = re.search(r'self\.__next_f\.push\(\[\d+,"(.*?)"\]\)', text, re.DOTALL)
        if not m:
            continue
        try:
            # Unescape the JSON-encoded string inside the push call
            raw_str = m.group(1).encode("raw_unicode_escape").decode("unicode_escape")
            json_start = raw_str.find("{")
            if json_start == -1:
                continue
            inner = json.loads(raw_str[json_start:])
            prod = _deep_find(inner, "name", "productName", depth=5)
            if prod and (prod.get("name") or prod.get("productName")):
                result = _normalize(prod)
                if result["name"]:
                    print(f"[HB hydration OK] {result['name']}")
                    return result
        except Exception:
            pass

    return None


def _hb_reviews(sku: str, max_reviews: int = 200) -> list[str]:
    if not sku:
        return []
    reviews: list[str] = []
    headers = _make_api_headers("https://www.hepsiburada.com")
    endpoints = [
        ("https://www.hepsiburada.com/reviews/api/v1/review/get",
         {"productId": sku, "page": 0, "pageSize": 20, "sortBy": "MOST_RECENT"}, "page", 20),
        ("https://www.hepsiburada.com/api/review/v2/reviews",
         {"sku": sku, "page": 0, "size": 32}, "page", 32),
        ("https://www.hepsiburada.com/api/ugc/reviews",
         {"productId": sku, "page": 0, "size": 32}, "page", 32),
        (f"https://reviews.hepsiburada.com/ugc/reviews/products/{sku}",
         {"offset": 0, "limit": 32}, "offset", 32),
    ]
    for base_url, base_params, page_key, page_size in endpoints:
        try:
            for page_num in range(7):
                offset = page_num * page_size if page_key == "offset" else page_num
                params = {**base_params, page_key: offset}
                resp = requests.get(base_url, params=params, headers=headers, timeout=10)
                if resp.status_code not in (200, 201):
                    break
                data = resp.json()
                items = data.get("reviews") or data.get("content") or data.get("data") or data.get("result") or []
                if isinstance(items, dict):
                    items = items.get("reviews") or items.get("content") or []
                if not items:
                    break
                for item in items:
                    t = _s(item.get("review") or item.get("comment") or item.get("text") or item.get("reviewText") or "")
                    if t and len(t) > 5:
                        reviews.append(t)
                if len(reviews) >= max_reviews or len(items) < 10:
                    break
                time.sleep(0.15)
            if reviews:
                break
        except Exception as e:
            print(f"[HB reviews error] {e}")
    print(f"[Hepsiburada] {len(reviews)} yorum")
    return reviews


def _hb_html_fallback(url: str, soup: BeautifulSoup) -> dict:
    ld = _json_ld(soup)
    ld_off = ld.get("offers", {})
    if isinstance(ld_off, list):
        ld_off = ld_off[0] if ld_off else {}
    name = ld.get("name") or _text(soup,
        '[data-test-id="title"]', '[class*="product-name"] h1',
        'h1[itemprop="name"]', "h1")
    brand = (ld.get("brand", {}).get("name") if isinstance(ld.get("brand"), dict) else "") or \
            _text(soup, '[data-test-id="brand"]', '[class*="brand"]')
    price = (f"₺{ld_off['price']}" if ld_off.get("price") else "") or \
            _text(soup, '[data-test-id="price-current-price"]', '[class*="product-price"]', '[itemprop="price"]')
    rating = _parse_rating(
        _s(ld.get("aggregateRating", {}).get("ratingValue")) or
        _text(soup, '[data-test-id="rating"]', '[class*="rating-score"]'))
    review_count = _parse_count(
        _s(ld.get("aggregateRating", {}).get("reviewCount")) or
        _text(soup, '[data-test-id="review-count"]', '[class*="review-count"]'))
    image = _og_image(soup)
    if not image:
        img_el = soup.select_one('[class*="product-image"] img') or soup.select_one('img[itemprop="image"]')
        if img_el:
            image = _abs_url(img_el.get("src") or img_el.get("data-src") or "", url)
    if not image and ld.get("image"):
        raw_img = ld["image"]
        image = raw_img[0] if isinstance(raw_img, list) else raw_img
    reviews = [el.get_text(strip=True) for el in
               soup.select('[data-test-id="review-text"], [class*="comment-content"], [class*="review-text"]')
               if len(el.get_text(strip=True)) > 15]
    category = ld.get("category") or _text(soup, '[class*="breadcrumb"] li:last-child')
    description = _text(soup, '[data-test-id="description"]', '[class*="product-description"]')[:600]
    return dict(name=name, brand=brand, price=price, rating=rating, image=image,
                category=category, review_count=review_count, reviews=reviews, description=description)


def _hb_extract(url: str, soup: BeautifulSoup | None) -> dict | None:
    sku = _hb_sku(url)

    # Fallback chain: API → Embedded state → JSON-LD+HTML
    if sku:
        data = _hb_api(sku)
        if data and _has_data(data):
            data["reviews"] = _hb_reviews(sku)
            return data

    if soup:
        data = _hb_embedded(soup)
        if data and _has_data(data):
            data["reviews"] = _hb_reviews(sku) if sku else []
            if not data["reviews"]:
                data["reviews"] = [el.get_text(strip=True) for el in
                                   soup.select('[data-test-id="review-text"], [class*="comment-content"], [class*="review-text"]')
                                   if len(el.get_text(strip=True)) > 15]
            return data
        return _hb_html_fallback(url, soup)

    return None

# ===========================================================================
# AMAZON extractor
# ===========================================================================

def _amz_asin(url: str) -> str | None:
    path = urlparse(url).path
    m = re.search(r"/dp/([A-Z0-9]{10})", path) or re.search(r"/([A-Z0-9]{10})(?:/|\?|$)", path)
    return m.group(1) if m else None


def _amz_parse_embedded(soup: BeautifulSoup) -> dict:
    """Parse Amazon embedded JSON sources: twister data, data-a-state, application/json scripts."""
    raw_html = str(soup)

    # 1. twister-js-init-dpx-data (rich product state)
    m = re.search(r'id="twister-js-init-dpx-data"[^>]*>(.*?)</script>', raw_html, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            if data.get("landingAsin") or data.get("buyboxTitleProductName"):
                return data
        except Exception:
            pass

    # 2. data-a-state attributes with product signals
    for tag in soup.find_all(attrs={"data-a-state": True}):
        try:
            state = json.loads(tag.get("data-a-state") or "{}")
            if isinstance(state, dict) and state.get("buyboxTitleProductName"):
                return state
        except Exception:
            pass

    # 3. Inline JSON in script[type="application/json"]
    for script in soup.find_all("script", type="application/json"):
        try:
            data = json.loads(script.string or "{}")
            if isinstance(data, dict) and (data.get("name") or data.get("title") or data.get("asin")):
                return data
        except Exception:
            pass

    return {}


def _amz_dynamic_image(json_str: str) -> str:
    try:
        data = json.loads(json_str)
        if data:
            return max(data.keys(), key=lambda u: data[u][0] * data[u][1] if data[u] else 0)
    except Exception:
        pass
    return ""


def _amz_reviews(asin: str, max_reviews: int = 150) -> list[str]:
    reviews: list[str] = []
    base = "https://www.amazon.com.tr"
    headers = {**_make_headers(), "Referer": f"{base}/dp/{asin}"}
    _captcha = frozenset(["validatecaptcha", "captchacharacters", "robot check", "automated access"])
    for page in range(1, 8):
        try:
            resp = requests.get(
                f"{base}/product-reviews/{asin}",
                params={"pageNumber": page, "reviewerType": "all_reviews", "sortBy": "recent"},
                headers=headers, timeout=12,
            )
            if resp.status_code != 200:
                break
            if any(s in resp.text.lower() for s in _captcha):
                print(f"[Amazon reviews CAPTCHA page {page}]")
                break
            s = BeautifulSoup(resp.text, "html.parser")
            page_reviews = [el.get_text(strip=True) for el in
                            s.select('[data-hook="review-body"] span, .review-text-content span')
                            if len(el.get_text(strip=True)) > 20]
            if not page_reviews:
                break
            reviews.extend(page_reviews)
            if len(reviews) >= max_reviews:
                break
            time.sleep(0.4)
        except Exception as e:
            print(f"[Amazon reviews error] {e}")
            break
    print(f"[Amazon] {len(reviews)} yorum")
    return reviews


def _amz_extract(url: str, soup: BeautifulSoup | None) -> dict | None:
    if not soup:
        return None

    asin = _amz_asin(url)
    ld = _json_ld(soup)
    embedded = _amz_parse_embedded(soup)

    name = (_s(embedded.get("buyboxTitleProductName")) or ld.get("name") or
            _text(soup, "#productTitle", "h1")).strip()
    brand_raw = ld.get("brand", {})
    brand = (brand_raw.get("name") if isinstance(brand_raw, dict) else "") or \
            _text(soup, "#bylineInfo", '[class*="brand"]')
    brand = re.sub(r"(?i)(marka|brand|ziyaret|visit|the store)[:\s]*", "", brand).strip()

    price_whole = _text(soup, ".a-price-whole")
    price_frac = _text(soup, ".a-price-fraction")
    price = (price_whole.rstrip(".,") + ("," + price_frac if price_frac else "") + " TL") if price_whole else \
            _text(soup, ".apexPriceToPay .a-offscreen", '[data-a-color="price"] .a-offscreen',
                  '[id*="priceblock"]', '[class*="price"]')

    rating = _parse_rating(
        _text(soup, '[data-hook="rating-out-of-text"]', ".a-icon-alt") or
        _s(ld.get("aggregateRating", {}).get("ratingValue")))
    review_count = _parse_count(
        _text(soup, "#acrCustomerReviewText", '[data-hook="total-review-count"]') or
        _s(ld.get("aggregateRating", {}).get("reviewCount")))

    image = ""
    img_el = soup.select_one("#landingImage") or soup.select_one("#imgBlkFront") or soup.select_one("#main-image")
    if img_el:
        dyn = img_el.get("data-a-dynamic-image", "")
        image = _amz_dynamic_image(dyn) if dyn else _abs_url(
            img_el.get("data-old-hires") or img_el.get("src") or "", url)
    if not image:
        image = _og_image(soup)

    description = _text(soup, "#feature-bullets", "#productDescription")[:600]
    reviews = [el.get_text(strip=True) for el in
               soup.select('[data-hook="review-body"] span, .review-text-content span')
               if len(el.get_text(strip=True)) > 20]
    if asin:
        more = _amz_reviews(asin)
        seen = set(reviews)
        reviews = (reviews + [r for r in more if r not in seen])[:300]

    category = ld.get("category") or _text(soup, ".a-breadcrumb li:last-child")

    return dict(name=name, brand=brand, price=price, rating=rating, image=image,
                category=category, review_count=review_count, reviews=reviews, description=description)

# ===========================================================================
# N11 / Generic extractors
# ===========================================================================

def _n11_extract(url: str, soup: BeautifulSoup) -> dict:
    ld = _json_ld(soup)
    name = ld.get("name") or _text(soup, 'h1[class*="title"]', "h1")
    brand = (ld.get("brand", {}).get("name") if isinstance(ld.get("brand"), dict) else "") or _text(soup, '[class*="brand"]')
    price = _text(soup, '[class*="newPrice"]', '[itemprop="price"]')
    rating = _parse_rating(_s(ld.get("aggregateRating", {}).get("ratingValue")) or _text(soup, '[class*="ratingScore"]'))
    review_count = _parse_count(_s(ld.get("aggregateRating", {}).get("reviewCount")) or _text(soup, '[class*="ratingCount"]'))
    img_el = soup.select_one('[class*="product-image"] img') or soup.select_one('img[itemprop="image"]')
    image = _abs_url(img_el.get("src") if img_el else "", url)
    reviews = [el.get_text(strip=True) for el in soup.select('[class*="comment"]') if len(el.get_text(strip=True)) > 15]
    description = _text(soup, '[class*="description"]')[:600]
    return dict(name=name, brand=brand, price=price, rating=rating, image=image,
                category="", review_count=review_count, reviews=reviews, description=description)


def _generic_extract(url: str, soup: BeautifulSoup) -> dict:
    ld = _json_ld(soup)
    ld_off = ld.get("offers", {})
    if isinstance(ld_off, list):
        ld_off = ld_off[0] if ld_off else {}
    name = ld.get("name") or _text(soup, 'h1[itemprop="name"]', "h1") or \
           (soup.title.get_text(strip=True) if soup.title else "Ürün")
    price = (f"₺{ld_off['price']}" if ld_off.get("price") else "") or _text(soup, '[itemprop="price"]', '[class*="price"]')
    brand = (ld.get("brand", {}).get("name") if isinstance(ld.get("brand"), dict) else "") or _text(soup, '[itemprop="brand"]')
    rating = _parse_rating(_s(ld.get("aggregateRating", {}).get("ratingValue")) or _text(soup, '[itemprop="ratingValue"]'))
    review_count = _parse_count(_s(ld.get("aggregateRating", {}).get("reviewCount")))
    img_el = (soup.select_one('[itemprop="image"]') or soup.select_one('img[class*="product"]')
              or soup.select_one('meta[property="og:image"]'))
    image = _abs_url(img_el.get("src") or img_el.get("content") or "" if img_el else "", url) or _og_image(soup)
    reviews = [el.get_text(strip=True) for el in
               soup.select('[class*="review"], [class*="comment"], [class*="yorum"], [itemprop="reviewBody"]')
               if len(el.get_text(strip=True)) > 30]
    description = _text(soup, '[class*="description"]', '[itemprop="description"]')[:600]
    return dict(name=name, brand=brand, price=price, rating=rating, image=image,
                category="", review_count=review_count, reviews=reviews, description=description)

# ===========================================================================
# Analysis helpers (sentiment, Gemini)
# ===========================================================================

_POSITIVE_WORDS = [
    "harika", "mükemmel", "güzel", "iyi", "kaliteli", "memnun", "tavsiye",
    "süper", "beğendim", "sevdim", "şahane", "kusursuz", "hızlı", "sağlam",
    "değer", "tatmin", "başarılı", "orijinal", "perfect", "great", "excellent",
    "amazing", "good", "best", "love", "happy", "satisfied", "recommend",
]
_NEGATIVE_WORDS = [
    "kötü", "berbat", "rezalet", "sorun", "problem", "arızalı", "sahte",
    "bozuk", "pahalı", "kalitesiz", "yanlış", "hatalı", "pişman", "şikayet",
    "hayal kırıklığı", "geç", "gecikme", "kırık", "hasarlı", "kopya",
    "bad", "terrible", "awful", "poor", "worst", "disappointed", "broken", "fake",
]
_POSITIVE_ASPECTS = {
    "Hızlı kargo ve teslimat": ["kargo", "hızlı geldi", "zamanında", "çabuk"],
    "Ürün kalitesi yüksek": ["kaliteli", "sağlam", "dayanıklı", "quality"],
    "Fiyat/performans dengesi iyi": ["fiyatına göre", "uygun fiyat", "para eder", "değer"],
    "Ürün açıklamayla uyuşuyor": ["beklediğim gibi", "tam açıklandığı gibi", "as described"],
    "Satıcı güvenilir": ["satıcı iyi", "güvenilir satıcı", "seller"],
    "Paketleme özenli": ["iyi paketlenmiş", "özenle paketlenmiş", "kutu sağlam"],
    "Kullanımı kolay": ["kolay kullanım", "pratik", "kullanışlı", "easy to use"],
    "Tasarım beğenildi": ["güzel tasarım", "şık", "estetik", "design"],
}
_NEGATIVE_ASPECTS = {
    "Kargo geç geldi": ["geç geldi", "gecikme", "uzun sürdü", "late delivery"],
    "Ürün açıklamayla uyuşmuyor": ["aldatıcı", "yanıltıcı", "farklı çıktı", "not as described"],
    "Kalite beklentiyi karşılamadı": ["kalitesiz", "kötü kalite", "ucuz malzeme", "poor quality"],
    "Fiyat yüksek": ["çok pahalı", "değmez", "overpriced", "expensive"],
    "Müşteri hizmetleri yetersiz": ["müşteri hizmet kötü", "cevap vermiyor", "bad service"],
    "Ürün hasarlı geldi": ["kırık geldi", "hasarlı", "bozuk geldi", "arrived broken"],
    "Sahte ürün şüphesi": ["sahte", "kopya", "taklit", "not original", "fake"],
    "İade süreci zorlu": ["iade ettim", "iade zor", "return problem"],
}
_AUDIENCE_MAP = {
    "Profesyoneller": (["iş", "profesyonel", "ofis", "çalışma", "professional", "office"], "work"),
    "Öğrenciler": (["öğrenci", "okul", "ders", "eğitim", "student", "school"], "school"),
    "Oyuncular": (["oyun", "gaming", "gamer", "oyuncu", "game"], "sports_esports"),
    "Gezginler": (["seyahat", "tatil", "taşınabilir", "portable", "travel"], "flight"),
    "Sporcular": (["spor", "fitness", "koşu", "egzersiz", "sport", "gym"], "fitness_center"),
    "Ev Kullanımı": (["ev", "mutfak", "aile", "günlük", "home", "kitchen", "family"], "home"),
    "Teknoloji Tutkunları": (["teknoloji", "teknik", "özellik", "performans", "tech", "specs"], "devices"),
    "Tasarımcılar": (["tasarım", "yaratıcı", "grafik", "görsel", "design", "creative"], "palette"),
}
_REC_ICONS = {
    "Kesinlikle Alınır": "task_alt",
    "Tavsiye Edilir": "check_circle",
    "Değerlendirilebilir": "lightbulb",
    "Dikkatli Olunmalı": "priority_high",
}


def _strip_json_fence(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    return re.sub(r"\s*```$", "", text, flags=re.MULTILINE).strip()


def _extract_json(text: str) -> dict:
    for pattern in (r"\{[\s\S]*?\}(?=\s*$)", r"\{[\s\S]+\}"):
        m = re.search(pattern, text)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return json.loads(text)


def _analyze_sentiment_local(reviews: list[str]) -> dict:
    pos = neg = 0
    for r in reviews:
        rl = r.lower()
        p = sum(1 for w in _POSITIVE_WORDS if w in rl)
        n = sum(1 for w in _NEGATIVE_WORDS if w in rl)
        if p > n:
            pos += 1
        elif n > p:
            neg += 1
    total = len(reviews) or 1
    positive = round(pos / total * 100)
    negative = round(neg / total * 100)
    return {"positive": positive, "neutral": max(0, 100 - positive - negative), "negative": negative}


def _extract_aspects(reviews: list[str], aspect_map: dict, max_items: int = 5) -> list[str]:
    all_text = " ".join(reviews).lower()
    return [aspect for aspect, kws in aspect_map.items() if any(kw in all_text for kw in kws)][:max_items]


def _get_audiences(product_info: dict, reviews: list[str]) -> list[dict]:
    all_text = " ".join(reviews + [product_info.get("name", ""),
                                   product_info.get("brand", ""),
                                   product_info.get("category", "")]).lower()
    found = [{"name": name, "icon": icon}
             for name, (kws, icon) in _AUDIENCE_MAP.items()
             if any(kw in all_text for kw in kws)]
    defaults = [{"name": "Genel Kullanım", "icon": "people"},
                {"name": "Ev Kullanımı", "icon": "home"},
                {"name": "Profesyoneller", "icon": "work"}]
    for d in defaults:
        if len(found) >= 3:
            break
        if not any(f["name"] == d["name"] for f in found):
            found.append(d)
    return found[:5]


def _get_trust_score(reviews: list[str], review_count: int) -> int:
    score = 65
    if reviews:
        avg_len = sum(len(r) for r in reviews) / len(reviews)
        score += 18 if avg_len > 100 else (10 if avg_len > 50 else 0)
    if review_count > 1000:
        score += 12
    elif review_count > 200:
        score += 6
    elif review_count > 50:
        score += 3
    return min(score, 98)


def _gemini_analyze(product_info: dict, reviews: list[str], description: str, lang: str) -> dict:
    name = product_info.get("name", "")
    brand = product_info.get("brand", "")
    price = product_info.get("price", "")
    rating = product_info.get("rating", 0)
    review_count = product_info.get("review_count", 0)
    category = product_info.get("category", "")

    ctx = [f"Ürün: {(brand + ' ' + name).strip()}"]
    if category:
        ctx.append(f"Kategori: {category}")
    if price:
        ctx.append(f"Fiyat: {price}")
    if rating:
        ctx.append(f"Puan: {rating}/5")
    if review_count:
        ctx.append(f"Toplam yorum sayısı: {review_count}")
    if description:
        ctx.append(f"Açıklama: {description[:400]}")

    review_section = ""
    if reviews:
        review_text = "\n".join(f"- {r}" for r in reviews[:25])
        review_section = f"\n\nKullanıcı Yorumları:\n{review_text}"

    lang_inst = LANG_PROMPTS.get(lang, LANG_PROMPTS["tr"])
    prompt = (
        lang_inst + "\n\n" + "\n".join(ctx) + review_section +
        "\n\nBu ürüne özel kapsamlı bir analiz yap. SADECE aşağıdaki JSON formatında yanıt ver:\n"
        '{\n'
        '  "sentiment": {"positive": <0-100>, "neutral": <0-100>, "negative": <0-100>},\n'
        '  "positives": ["<olumlu özellik>", "<olumlu özellik>", "<olumlu özellik>"],\n'
        '  "negatives": ["<olumsuz özellik>", "<olumsuz özellik>"],\n'
        '  "summary": "<2-3 cümlelik doğal özet>",\n'
        '  "recommendation": "<Kesinlikle Alınır | Tavsiye Edilir | Değerlendirilebilir | Dikkatli Olunmalı>",\n'
        '  "audiences": [{"name": "<hedef kitle>", "icon": "<material icon>"}, ...],\n'
        '  "price_estimate": "<tahmini fiyat aralığı, örn: 8.500 - 12.000 TL>",\n'
        '  "review_count_estimate": <tahmini yorum sayısı tam sayı>\n'
        '}'
    )

    resp = _genai_client.models.generate_content(model=_GEMINI_MODEL, contents=prompt)
    data = _extract_json(_strip_json_fence(resp.text.strip()))

    s = data.get("sentiment", {})
    pos = max(0, min(100, int(s.get("positive", 65))))
    neg = max(0, min(100, int(s.get("negative", 10))))
    neu = max(0, 100 - pos - neg)

    rec = data.get("recommendation", "Değerlendirilebilir")
    rec_icon = next((v for k, v in _REC_ICONS.items() if k in rec), "lightbulb")
    rec = next((k for k in _REC_ICONS if k in rec), "Değerlendirilebilir")

    return {
        "sentiment": {"positive": pos, "neutral": neu, "negative": neg},
        "positives": [p for p in data.get("positives", []) if p][:5],
        "negatives": [n for n in data.get("negatives", []) if n][:5],
        "summary": data.get("summary", ""),
        "recommendation": rec,
        "recommendation_icon": rec_icon,
        "audiences": data.get("audiences", [])[:5],
        "price_estimate": str(data.get("price_estimate", "") or ""),
        "review_count_estimate": int(data.get("review_count_estimate", 0) or 0),
    }


def _generate_summary(product_info: dict, sentiment: dict, positives: list, negatives: list) -> str:
    name = product_info.get("name", "Bu ürün")
    brand = product_info.get("brand", "")
    review_count = product_info.get("review_count", 0)
    full_name = f"{brand} {name}".strip() if brand else name
    try:
        prompt = (
            f"'{full_name}' adlı ürün için {review_count} yorum analiz edildi.\n"
            f"Duygu dağılımı: %{sentiment.get('positive', 65)} pozitif, %{sentiment.get('negative', 10)} negatif.\n"
            f"Olumlu yönler: {', '.join(positives[:3]) if positives else 'belirsiz'}.\n"
            f"Olumsuz yönler: {', '.join(negatives[:2]) if negatives else 'belirsiz'}.\n\n"
            "Bu bilgilere göre ürün için doğal ve akıcı Türkçe ile 2-3 cümlelik bir özet yaz. Sadece özeti yaz."
        )
        resp = _genai_client.models.generate_content(model=_GEMINI_MODEL, contents=prompt)
        return resp.text.strip()
    except Exception as e:
        print(f"[Gemini summary error] {e}")
    pos_pct = sentiment.get("positive", 65)
    count_str = f"{review_count} yorum" if review_count > 0 else "mevcut yorumlar"
    verdict = (f"kullanıcıların %{pos_pct}'i üründen memnun" if pos_pct >= 75 else
               f"yorumlar genel olarak olumlu (%{pos_pct} pozitif)" if pos_pct >= 55 else
               f"yorumlar karışık (%{pos_pct} olumlu, %{sentiment.get('negative', 0)} olumsuz)" if pos_pct >= 40 else
               f"kullanıcıların büyük çoğunluğu üründen memnun değil")
    summary = f"{full_name} için {count_str} analiz edildi; {verdict}."
    if positives:
        summary += f" Öne çıkan olumlu yönler: {', '.join(positives[:2])}."
    if negatives:
        summary += f" En çok şikayet edilen: {', '.join(negatives[:1])}."
    return summary


def _get_recommendation_local(sentiment: dict, rating: float) -> tuple[str, str]:
    pos = sentiment.get("positive", 65)
    if pos >= 75 or rating >= 4.5:
        return "Kesinlikle Alınır", _REC_ICONS["Kesinlikle Alınır"]
    if pos >= 60 or rating >= 4.0:
        return "Tavsiye Edilir", _REC_ICONS["Tavsiye Edilir"]
    if pos >= 45:
        return "Değerlendirilebilir", _REC_ICONS["Değerlendirilebilir"]
    return "Dikkatli Olunmalı", _REC_ICONS["Dikkatli Olunmalı"]

# ===========================================================================
# Gemini search grounding fallback
# ===========================================================================

def _fetch_via_search(url: str) -> dict:
    """Use Gemini search grounding to retrieve product data when scraping fails."""
    name = _name_from_url(url)
    site = _detect_site(url)
    site_domain = {"hepsiburada": "hepsiburada.com", "trendyol": "trendyol.com",
                   "amazon": "amazon.com.tr", "n11": "n11.com"}.get(site, site)
    prompt = (
        f"Bu ürünü {site_domain} sitesinde Google arama sonuçlarından bul:\n"
        f"URL: {url}\nTahmini ürün: {name}\n\n"
        "Bulduğun gerçek verileri SADECE şu JSON formatında döndür:\n"
        '{"name":"<tam ürün adı>","brand":"<marka>","price":"<güncel TL fiyatı>",'
        '"rating":<5 üzerinden>,"review_count":<tam sayı>,"image_url":"<CDN görsel URL>",'
        '"category":"<kategori>"}'
    )
    try:
        resp = _genai_client.models.generate_content(
            model=_GEMINI_MODEL, contents=prompt,
            config=genai_types.GenerateContentConfig(
                tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())]
            ),
        )
        data = _extract_json(_strip_json_fence(resp.text.strip()))
        image = data.get("image_url", "")
        if not _valid_img(image):
            image = ""
        return {
            "name": data.get("name") or name,
            "brand": data.get("brand", ""),
            "price": data.get("price", ""),
            "rating": _sf(data.get("rating", 0)),
            "image": image,
            "category": data.get("category", ""),
            "review_count": _si(data.get("review_count", 0)),
            "reviews": [],
            "description": "",
        }
    except Exception as e:
        print(f"[Search grounding error] {e}")
        return {"name": name, "brand": "", "price": "", "rating": 0,
                "image": "", "category": "", "review_count": 0, "reviews": [], "description": ""}

# ===========================================================================
# Main analysis orchestrator
# ===========================================================================

class RealAnalyzer:
    """Orchestrates page fetching, extraction, and AI analysis."""

    def __init__(self, url: str, lang: str = "tr"):
        self.url = url
        self.lang = lang
        self.soup: BeautifulSoup | None = None

    def _fetch_html(self) -> bool:
        site = _detect_site(self.url)
        sess = _create_session(site)
        resp = _get(self.url, sess)
        if resp is None:
            return False

        # Fix encoding
        if resp.apparent_encoding and "utf-8" not in (resp.encoding or "").lower():
            resp.encoding = resp.apparent_encoding
        elif not resp.encoding:
            resp.encoding = "utf-8"

        if _is_bot_page(resp.text):
            print(f"[Bot protection detected] {self.url[:70]}")
            self.soup = BeautifulSoup("", "html.parser")
            return False

        self.soup = BeautifulSoup(resp.text, "html.parser")
        title_el = self.soup.find("title")
        title_text = (title_el.get_text() or "").lower() if title_el else ""
        body_text = self.soup.get_text(strip=True)
        if len(body_text) < 500 or any(s in title_text for s in ("robot", "captcha", "access denied", "blocked")):
            print(f"[Thin/blocked page] {self.url[:70]}")
            return False
        return True

    def _run_extractor(self, site: str) -> dict | None:
        extractors = {
            "trendyol": lambda: _ty_extract(self.url, self.soup),
            "hepsiburada": lambda: _hb_extract(self.url, self.soup),
            "amazon": lambda: _amz_extract(self.url, self.soup),
            "n11": lambda: _n11_extract(self.url, self.soup),
            "generic": lambda: _generic_extract(self.url, self.soup),
        }
        return extractors.get(site, extractors["generic"])()

    def _try_playwright(self, site: str) -> dict | None:
        """Render page via Playwright and re-run extractor."""
        html = _render_playwright(self.url)
        if not html:
            return None
        self.soup = BeautifulSoup(html, "html.parser")
        return self._run_extractor(site)

    def analyze(self) -> dict:
        site = _detect_site(self.url)
        page_fetched = self._fetch_html()
        product_info: dict = {}

        if page_fetched:
            product_info = self._run_extractor(site) or {}

        # Playwright fallback when HTTP fetch returned a bot page or thin content
        if not _has_data(product_info):
            if not page_fetched:
                print(f"[Trying Playwright] {self.url[:70]}")
                pw_data = self._try_playwright(site)
                if pw_data and _has_data(pw_data):
                    product_info = pw_data
                    page_fetched = True
                    print(f"[Playwright extraction OK] {product_info['name']}")

        # Search grounding fallback
        if not _has_data(product_info):
            print(f"[Search grounding] {self.url[:70]}")
            product_info = _fetch_via_search(self.url)
            page_fetched = False

        # Ensure OG image if missing after page fetch
        if page_fetched and self.soup and not product_info.get("image"):
            product_info["image"] = _og_image(self.soup)

        description = product_info.pop("description", "") or (
            _meta_desc(self.soup) if page_fetched and self.soup else ""
        )
        reviews: list[str] = product_info.pop("reviews", [])
        review_count = product_info.get("review_count", 0) or len(reviews)
        product_info["review_count"] = review_count

        price_estimated = False
        review_count_estimated = False

        try:
            ai = _gemini_analyze(product_info, reviews, description, self.lang)
            sentiment = ai["sentiment"]
            positives = ai["positives"]
            negatives = ai["negatives"]
            summary = ai["summary"]
            recommendation = ai["recommendation"]
            rec_icon = ai["recommendation_icon"]
            audiences = ai["audiences"]

            if not product_info.get("price") and ai.get("price_estimate"):
                product_info["price"] = ai["price_estimate"]
                price_estimated = True
            if not review_count and ai.get("review_count_estimate", 0) > 0:
                review_count = ai["review_count_estimate"]
                product_info["review_count"] = review_count
                review_count_estimated = True

        except Exception as e:
            print(f"[Gemini full analysis error] {e}")
            sentiment = _analyze_sentiment_local(reviews)
            positives = _extract_aspects(reviews, _POSITIVE_ASPECTS) or (
                ["Genel kullanıcı memnuniyeti yüksek", "Ürün beklentileri karşılıyor"]
                if sentiment["positive"] > 55 else ["Bazı kullanıcılar üründen memnun"]
            )
            negatives = _extract_aspects(reviews, _NEGATIVE_ASPECTS) or (
                ["Belirgin şikayet kategorisi tespit edilmedi"]
                if sentiment["negative"] < 25 else ["Bazı kullanıcılar sorun yaşamış"]
            )
            recommendation, rec_icon = _get_recommendation_local(sentiment, product_info.get("rating", 0))
            summary = _generate_summary(product_info, sentiment, positives, negatives)
            audiences = _get_audiences(product_info, reviews)

        product_info["price_estimated"] = price_estimated
        trust_score = _get_trust_score(reviews, review_count)

        if trust_score >= 85:
            risk_label, risk_icon, risk_color = "Düşük Risk", "verified", "text-primary-container"
        elif trust_score >= 70:
            risk_label, risk_icon, risk_color = "Orta Risk", "info", "text-secondary"
        else:
            risk_label, risk_icon, risk_color = "Yüksek Risk", "warning", "text-error"

        return {
            "product": product_info,
            "recommendation": recommendation,
            "recommendation_icon": rec_icon,
            "positives": positives,
            "negatives": negatives,
            "audiences": audiences,
            "sentiment": sentiment,
            "trust_score": trust_score,
            "risk_label": risk_label,
            "risk_icon": risk_icon,
            "risk_color": risk_color,
            "review_count": review_count,
            "review_count_estimated": review_count_estimated,
            "page_accessible": page_fetched,
            "summary": summary,
            "url": self.url,
            "site": site,
        }

# ===========================================================================
# Analysis storage
# ===========================================================================

def save_analysis(result: dict) -> str:
    aid = secrets.token_urlsafe(16)
    path = os.path.join(_ANALYSIS_DIR, f"{aid}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    return aid


def load_analysis(aid: str) -> dict | None:
    if not aid:
        return None
    path = os.path.join(_ANALYSIS_DIR, f"{aid}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

# ===========================================================================
# User auth helpers
# ===========================================================================

def load_users() -> dict:
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_users(users: dict) -> None:
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

# ===========================================================================
# Flask routes
# ===========================================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["GET", "POST"])
def analyze_route():
    if request.method == "GET":
        return render_template("index.html")

    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    lang = (data.get("lang") or "tr").strip()
    if lang not in LANG_PROMPTS:
        lang = "tr"
    if not url:
        return jsonify({"error": "URL gerekli"}), 400
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url

    session["lang"] = lang
    analyzer = RealAnalyzer(url, lang=lang)
    result = analyzer.analyze()

    if result is None:
        return jsonify({"error": "Ürün sayfasına erişilemedi. Lütfen geçerli bir ürün linki girin."}), 422

    aid = save_analysis(result)
    session["analysis_id"] = aid
    return jsonify({"success": True, "redirect": "/results"})


@app.route("/results")
def results():
    analysis = load_analysis(session.get("analysis_id"))
    if not analysis:
        return render_template("index.html")
    return render_template("results.html", data=analysis)


@app.route("/loading")
def loading():
    return render_template("loading.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/api/results")
def api_results():
    analysis = load_analysis(session.get("analysis_id"))
    if not analysis:
        return jsonify({"error": "Analiz bulunamadı"}), 404
    return jsonify(analysis)


# ----- Auth -----

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not name or not email or not password:
        return jsonify({"error": "Tüm alanlar zorunludur"}), 400
    if len(password) < 6:
        return jsonify({"error": "Şifre en az 6 karakter olmalıdır"}), 400
    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        return jsonify({"error": "Geçerli bir e-posta girin"}), 400

    users = load_users()
    if email in users:
        return jsonify({"error": "Bu e-posta adresi zaten kayıtlı"}), 409

    users[email] = {
        "name": name, "email": email,
        "password": hash_password(password),
        "created_at": datetime.now().isoformat(),
    }
    save_users(users)
    session["user"] = {"name": name, "email": email}
    return jsonify({"success": True, "name": name})


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "E-posta ve şifre gereklidir"}), 400

    users = load_users()
    user = users.get(email)
    if not user or user["password"] != hash_password(password):
        return jsonify({"error": "E-posta veya şifre hatalı"}), 401

    session["user"] = {"name": user["name"], "email": email}
    return jsonify({"success": True, "name": user["name"]})


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("index"))


@app.route("/proxy-image")
def proxy_image():
    url = request.args.get("url", "").strip()
    if not url or not url.startswith("http"):
        return "", 400
    try:
        resp = requests.get(url, headers=_make_headers(), timeout=8, stream=True)
        content_type = resp.headers.get("Content-Type", "image/jpeg")
        from flask import Response
        return Response(resp.content, content_type=content_type)
    except Exception:
        return "", 502


# ----- Chat -----

@app.route("/api/chat", methods=["POST"])
def chat_api():
    data = request.get_json(force=True, silent=True) or {}
    user_message = (data.get("user_message") or "").strip()
    product_context = data.get("product_context") or {}
    history = data.get("chat_history") or []

    if not user_message:
        return jsonify({"error": "Mesaj boş olamaz", "success": False}), 400

    ctx_parts = []
    if product_context:
        for key, label in [("name", "Ürün"), ("brand", "Marka"), ("price", "Fiyat")]:
            if product_context.get(key):
                ctx_parts.append(f"{label}: {product_context[key]}")
        if product_context.get("rating"):
            ctx_parts.append(f"Puan: {product_context['rating']}/5")

    system_instruction = (
        "Sen ShopMind AI adlı bir e-ticaret asistanısın. "
        "Kullanıcıların ürün satın alma kararlarına yardımcı olursun. "
        "Samimi, bilgilendirici ve kısa yanıtlar ver. Türkçe konuş."
    )
    if ctx_parts:
        system_instruction += "\n\nŞu anda analiz edilen ürün:\n" + "\n".join(ctx_parts)

    raw_history = []
    for msg in history[-12:]:
        role = "user" if msg.get("role") == "user" else "model"
        text = (msg.get("text") or "").strip()
        if text:
            raw_history.append({"role": role, "parts": [{"text": text}]})

    # Deduplicate consecutive same-role messages and ensure starts with user
    contents = []
    last_role = None
    for item in raw_history:
        if item["role"] != last_role:
            contents.append(item)
            last_role = item["role"]
    while contents and contents[0]["role"] != "user":
        contents.pop(0)
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    reply_text = None

    try:
        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
        )
        resp = _genai_client.models.generate_content(model=_GEMINI_MODEL, contents=contents, config=config)
        reply_text = resp.text
    except Exception as e:
        print(f"[Chat grounding error] {e}")

    if reply_text is None:
        try:
            resp = _genai_client.models.generate_content(
                model=_GEMINI_MODEL, contents=contents,
                config=genai_types.GenerateContentConfig(system_instruction=system_instruction),
            )
            reply_text = resp.text
        except Exception as e:
            print(f"[Chat plain error] {e}")

    if reply_text:
        return jsonify({"response": reply_text, "success": True})

    return jsonify({"error": "Asistan şu an yanıt veremiyor. Lütfen tekrar deneyin.", "success": False}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
