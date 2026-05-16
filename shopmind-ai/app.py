from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import requests
from bs4 import BeautifulSoup
import re
import json
import hashlib
import os
import random
from datetime import datetime
from google import genai as google_genai
from google.genai import types as genai_types

GEMINI_API_KEY = "AIzaSyCn_n1W52G9ao_NEwkjUdeAmAhGw8vtB2k"
_genai_client = google_genai.Client(api_key=GEMINI_API_KEY)
_GEMINI_MODEL = "gemini-2.5-flash"

LANG_PROMPTS = {
    'tr': 'Tüm metin içeriklerini (özet, özellikler, hedef kitle vb.) Türkçe yaz.',
    'en': 'Write all text content (summary, features, audiences, etc.) in English.',
    'de': 'Schreibe alle Texte (Zusammenfassung, Merkmale, Zielgruppen usw.) auf Deutsch.',
    'fr': 'Écris tous les textes (résumé, caractéristiques, publics cibles, etc.) en français.',
    'es': 'Escribe todo el contenido (resumen, características, audiencias, etc.) en español.',
    'ar': 'اكتب جميع النصوص (الملخص والميزات والفئات المستهدفة وما إلى ذلك) باللغة العربية.',
    'ru': 'Пиши весь текстовый контент (резюме, характеристики, целевую аудиторию и т.д.) на русском языке.',
    'zh': '用中文写所有文本内容（摘要、特点、目标受众等）。',
}

app = Flask(__name__)
app.secret_key = "shopmind-ai-secret-key-2024"

USERS_FILE = os.path.join(os.path.dirname(__file__), 'users.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Referer': 'https://www.google.com/',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'cross-site',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0',
    'sec-ch-ua': '"Google Chrome";v="124", "Chromium";v="124", "Not-A.Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
}

# ============================================================
# USER AUTH HELPERS
# ============================================================

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


# ============================================================
# REAL ANALYZER
# ============================================================

class RealAnalyzer:
    POSITIVE_WORDS = [
        'harika', 'mükemmel', 'güzel', 'iyi', 'kaliteli', 'memnun', 'tavsiye',
        'süper', 'beğendim', 'sevdim', 'şahane', 'kusursuz', 'hızlı', 'sağlam',
        'değer', 'tatmin', 'başarılı', 'orijinal', 'perfect', 'great', 'excellent',
        'amazing', 'good', 'best', 'love', 'happy', 'satisfied', 'recommend',
        'muhteşem', 'fevkalade', 'şık', 'pratik', 'kullanışlı',
    ]

    NEGATIVE_WORDS = [
        'kötü', 'berbat', 'rezalet', 'sorun', 'problem', 'arızalı', 'sahte',
        'bozuk', 'pahalı', 'kalitesiz', 'yanlış', 'hatalı', 'pişman', 'şikayet',
        'hayal kırıklığı', 'geç', 'gecikme', 'kırık', 'hasarlı', 'kopya',
        'bad', 'terrible', 'awful', 'poor', 'worst', 'disappointed', 'broken',
        'fake', 'useless', 'waste', 'return', 'refund',
    ]

    POSITIVE_ASPECTS = {
        'Hızlı kargo ve teslimat': ['kargo', 'hızlı geldi', 'zamanında', 'çabuk', 'hızlı teslimat'],
        'Ürün kalitesi yüksek': ['kaliteli', 'sağlam', 'dayanıklı', 'kalite çok iyi', 'quality'],
        'Fiyat/performans dengesi iyi': ['fiyatına göre', 'uygun fiyat', 'para eder', 'değer', 'ucuz'],
        'Ürün açıklamayla uyuşuyor': ['beklediğim gibi', 'tam açıklandığı gibi', 'uygun', 'as described'],
        'Satıcı güvenilir': ['satıcı iyi', 'güvenilir satıcı', 'satıcıya güvendim', 'seller'],
        'Paketleme özenli': ['iyi paketlenmiş', 'özenle paketlenmiş', 'packaging', 'kutu sağlam'],
        'Kullanımı kolay': ['kolay kullanım', 'pratik', 'kullanışlı', 'easy to use', 'simple'],
        'Tasarım beğenildi': ['güzel tasarım', 'şık', 'estetik', 'görünüm güzel', 'design'],
    }

    NEGATIVE_ASPECTS = {
        'Kargo geç geldi': ['geç geldi', 'gecikme', 'uzun sürdü', 'gecikmeli', 'late delivery'],
        'Ürün açıklamayla uyuşmuyor': ['aldatıcı', 'yanıltıcı', 'farklı çıktı', 'not as described'],
        'Kalite beklentiyi karşılamadı': ['kalitesiz', 'kötü kalite', 'ucuz malzeme', 'poor quality'],
        'Fiyat yüksek': ['çok pahalı', 'değmez', 'overpriced', 'expensive'],
        'Müşteri hizmetleri yetersiz': ['müşteri hizmet kötü', 'cevap vermiyor', 'bad service'],
        'Ürün hasarlı geldi': ['kırık geldi', 'hasarlı', 'bozuk geldi', 'arrived broken', 'damaged'],
        'Sahte ürün şüphesi': ['sahte', 'kopya', 'taklit', 'not original', 'fake'],
        'İade süreci zorlu': ['iade ettim', 'iade zor', 'return problem', 'geri gönderdim'],
    }

    AUDIENCE_MAP = {
        'Profesyoneller': (['iş', 'profesyonel', 'ofis', 'çalışma', 'professional', 'office'], 'work'),
        'Öğrenciler': (['öğrenci', 'okul', 'ders', 'eğitim', 'student', 'school'], 'school'),
        'Oyuncular': (['oyun', 'gaming', 'gamer', 'oyuncu', 'game'], 'sports_esports'),
        'Gezginler': (['seyahat', 'tatil', 'taşınabilir', 'portable', 'travel'], 'flight'),
        'Sporcular': (['spor', 'fitness', 'koşu', 'egzersiz', 'sport', 'gym'], 'fitness_center'),
        'Ev Kullanımı': (['ev', 'mutfak', 'aile', 'günlük', 'home', 'kitchen', 'family'], 'home'),
        'Teknoloji Tutkunları': (['teknoloji', 'teknik', 'özellik', 'performans', 'tech', 'specs'], 'devices'),
        'Tasarımcılar': (['tasarım', 'yaratıcı', 'grafik', 'görsel', 'design', 'creative'], 'palette'),
    }

    def __init__(self, url, lang='tr'):
        self.url = url
        self.lang = lang
        self.soup = None

    def fetch_page(self):
        http_session = requests.Session()
        http_session.headers.update(HEADERS)
        try:
            resp = http_session.get(self.url, timeout=15, allow_redirects=True)
            resp.raise_for_status()
            # Don't override utf-8 from Content-Type; apparent_encoding fails on gzip
            if resp.apparent_encoding and 'utf-8' not in (resp.encoding or '').lower():
                resp.encoding = resp.apparent_encoding
            elif not resp.encoding:
                resp.encoding = 'utf-8'
            self.soup = BeautifulSoup(resp.text, 'html.parser')
            return True
        except Exception as e:
            print(f"[Fetch error] {e}")
            return False

    def detect_site(self):
        u = self.url.lower()
        if 'trendyol.com' in u:
            return 'trendyol'
        if 'hepsiburada.com' in u:
            return 'hepsiburada'
        if 'amazon.com' in u:
            return 'amazon'
        if 'n11.com' in u:
            return 'n11'
        if 'gittigidiyor.com' in u:
            return 'gittigidiyor'
        return 'generic'

    # ---- JSON-LD structured data (works on many sites) ----
    def extract_json_ld(self):
        for script in self.soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string or '{}')
                if isinstance(data, list):
                    data = data[0]
                if data.get('@type') in ('Product', 'ItemPage', 'WebPage'):
                    return data
            except Exception:
                pass
        return {}

    def _clean_price(self, text):
        text = text.strip()
        text = re.sub(r'\s+', ' ', text)
        return text

    def _parse_rating(self, text):
        if not text:
            return 0.0
        m = re.search(r'[\d]+[,.][\d]+|[\d]+', text)
        if not m:
            return 0.0
        val = float(m.group().replace(',', '.'))
        return val if val <= 5 else val / 10.0

    def _abs_image(self, src):
        if not src:
            return ''
        src = src.strip()
        if src.startswith('//'):
            return 'https:' + src
        if src.startswith('/'):
            from urllib.parse import urlparse
            p = urlparse(self.url)
            return f"{p.scheme}://{p.netloc}{src}"
        return src

    # ---- Site-specific extractors ----

    def extract_trendyol(self):
        # Primary: __envoy__SHARED_PROPS (Trendyol's current SSR data structure)
        shared = self._extract_trendyol_embedded()
        prod = shared.get('product', {})

        # Fallback: JSON-LD (occasionally present)
        ld = self.extract_json_ld()

        name = (prod.get('name') or ld.get('name') or
                self._text('h1[class*="pr-new-br"]') or self._text('h1'))

        brand_raw = prod.get('brand', {})
        brand = (brand_raw.get('name', '') if isinstance(brand_raw, dict) else str(brand_raw or '')) or \
                (ld.get('brand', {}).get('name', '') if isinstance(ld.get('brand'), dict) else '') or \
                self._text('[class*="brand"]')

        # Rating & review count from ratingScore
        rating_score = prod.get('ratingScore', {}) if isinstance(prod.get('ratingScore'), dict) else {}
        rating = float(rating_score.get('averageRating', 0) or 0)
        review_count = int(rating_score.get('totalCount', 0) or rating_score.get('commentCount', 0) or 0)

        # Price: not in static HTML on Trendyol — try og:price meta, then leave empty for Gemini
        price = ''
        og_price_el = self.soup.find('meta', attrs={'property': 'product:price:amount'})
        if og_price_el and og_price_el.get('content'):
            price = f"₺{og_price_el['content']}"
        if not price:
            ld_offers = ld.get('offers', {})
            if isinstance(ld_offers, list):
                ld_offers = ld_offers[0] if ld_offers else {}
            if ld_offers.get('price'):
                price = f"₺{ld_offers['price']}"

        # Image: og:image is reliably in Trendyol's SSR HTML
        image = ''
        og_img = self.soup.find('meta', attrs={'property': 'og:image'})
        if og_img and og_img.get('content'):
            image = og_img['content']
        if not image:
            preload = self.soup.find('link', rel='preload', attrs={'as': 'image'})
            if preload and preload.get('href'):
                image = preload['href']

        category = ''
        cat = prod.get('category', {})
        if isinstance(cat, dict):
            category = cat.get('name', '')

        reviews = [el.get_text(strip=True) for el in self.soup.select('.comment-text, [class*="rnr-com-tx"]')
                   if len(el.get_text(strip=True)) > 15]

        return dict(name=name, brand=brand, price=price, rating=rating,
                    image=image, category=category, review_count=review_count, reviews=reviews)

    def extract_hepsiburada(self):
        ld = self.extract_json_ld()

        name = (ld.get('name') or
                self._text('[data-test-id="title"]') or
                self._text('[class*="product-name"] h1') or
                self._text('h1[itemprop="name"]') or
                self._text('h1'))

        brand = (ld.get('brand', {}).get('name', '') if isinstance(ld.get('brand'), dict) else '') or \
                self._text('[data-test-id="brand"]') or \
                self._text('[class*="merchant"] a') or self._text('[class*="brand"]')

        # Price: JSON-LD first, then meta og:price, then DOM
        ld_offers = ld.get('offers', {})
        if isinstance(ld_offers, list):
            ld_offers = ld_offers[0] if ld_offers else {}
        price = ''
        if ld_offers.get('price'):
            price = f"₺{ld_offers['price']}"
        if not price:
            og_price = self.soup.find('meta', attrs={'property': 'product:price:amount'})
            if og_price and og_price.get('content'):
                price = f"₺{og_price['content']}"
        if not price:
            price = (self._text('[data-test-id="price-current-price"]') or
                     self._text('[class*="product-price"]') or
                     self._text('[itemprop="price"]'))

        rating_val = str(ld.get('aggregateRating', {}).get('ratingValue', ''))
        rating = self._parse_rating(rating_val or
                                    self._text('[data-test-id="rating"]') or
                                    self._text('[class*="rating-score"]'))

        review_count_raw = str(ld.get('aggregateRating', {}).get('reviewCount', ''))
        review_count = self._parse_count(review_count_raw) if review_count_raw else \
                       self._parse_count(self._text('[data-test-id="review-count"]') or
                                         self._text('[class*="review-count"]'))

        # Image: og:image most reliable for Hepsiburada SSR
        image = ''
        og_img = self.soup.find('meta', attrs={'property': 'og:image'})
        if og_img and og_img.get('content'):
            image = og_img['content']
        if not image:
            img_el = (self.soup.select_one('[class*="product-image"] img') or
                      self.soup.select_one('img[itemprop="image"]'))
            if img_el:
                image = self._abs_image(img_el.get('src') or img_el.get('data-src') or '')
        if not image and ld.get('image'):
            raw_img = ld['image']
            image = raw_img[0] if isinstance(raw_img, list) else raw_img

        reviews = [el.get_text(strip=True) for el in
                   self.soup.select('[data-test-id="review-text"], [class*="comment-content"], [class*="review-text"]')
                   if len(el.get_text(strip=True)) > 15]

        category = ld.get('category') or self._text('[class*="breadcrumb"] li:last-child') or ''

        return dict(name=name, brand=brand, price=price, rating=rating,
                    image=image, category=category, review_count=review_count, reviews=reviews)

    def extract_amazon(self):
        ld = self.extract_json_ld()

        name = (ld.get('name') or
                self._text('#productTitle') or
                self._text('h1'))

        brand_el = self.soup.select_one('#bylineInfo') or self.soup.select_one('[class*="brand"]')
        brand_raw = (ld.get('brand', {}).get('name', '') if isinstance(ld.get('brand'), dict) else '') or \
                    (brand_el.get_text(strip=True) if brand_el else '')
        brand = re.sub(r'(?i)(marka|brand|ziyaret|visit)[:\s]*', '', brand_raw).strip()

        price_whole = self._text('.a-price-whole')
        price_frac = self._text('.a-price-fraction')
        if price_whole:
            price = price_whole.rstrip('.,') + (',' + price_frac if price_frac else '') + ' TL'
        else:
            price = self._text('[class*="price"]') or ''

        rating = self._parse_rating(self._text('[data-hook="rating-out-of-text"]') or
                                    self._text('.a-icon-alt'))
        review_count = self._parse_count(self._text('#acrCustomerReviewText') or
                                         self._text('[data-hook="total-review-count"]'))

        img_el = self.soup.select_one('#landingImage') or self.soup.select_one('#imgBlkFront')
        image = self._abs_image(img_el.get('src') or img_el.get('data-old-hires') if img_el else '')

        reviews = [el.get_text(strip=True) for el in
                   self.soup.select('[data-hook="review-body"] span, .review-text-content span')
                   if len(el.get_text(strip=True)) > 20]

        category = ld.get('category') or self._text('.a-breadcrumb li:last-child') or ''

        return dict(name=name, brand=brand, price=price, rating=rating,
                    image=image, category=category, review_count=review_count, reviews=reviews)

    def extract_n11(self):
        ld = self.extract_json_ld()
        name = ld.get('name') or self._text('h1[class*="title"]') or self._text('h1')
        brand = (ld.get('brand', {}).get('name', '') if isinstance(ld.get('brand'), dict) else '') or \
                self._text('[class*="brand"]')
        price = self._text('[class*="newPrice"]') or self._text('[itemprop="price"]') or ''
        rating = self._parse_rating(str(ld.get('aggregateRating', {}).get('ratingValue', '')) or
                                    self._text('[class*="ratingScore"]'))
        review_count = self._parse_count(str(ld.get('aggregateRating', {}).get('reviewCount', '')) or
                                         self._text('[class*="ratingCount"]'))
        img_el = self.soup.select_one('[class*="product-image"] img') or self.soup.select_one('img[itemprop="image"]')
        image = self._abs_image(img_el.get('src') if img_el else '')
        reviews = [el.get_text(strip=True) for el in self.soup.select('[class*="comment"]')
                   if len(el.get_text(strip=True)) > 15]
        return dict(name=name, brand=brand, price=price, rating=rating,
                    image=image, category='', review_count=review_count, reviews=reviews)

    def extract_generic(self):
        ld = self.extract_json_ld()
        name = (ld.get('name') or
                self._text('h1[itemprop="name"]') or
                self._text('h1') or
                (self.soup.title.get_text(strip=True) if self.soup.title else 'Ürün'))

        ld_offers = ld.get('offers', {})
        if isinstance(ld_offers, list):
            ld_offers = ld_offers[0] if ld_offers else {}
        price = (f"₺{ld_offers['price']}" if ld_offers.get('price') else '') or \
                self._text('[itemprop="price"]') or self._text('[class*="price"]') or ''

        brand = (ld.get('brand', {}).get('name', '') if isinstance(ld.get('brand'), dict) else '') or \
                self._text('[itemprop="brand"]') or ''

        rating = self._parse_rating(str(ld.get('aggregateRating', {}).get('ratingValue', '')) or
                                    self._text('[itemprop="ratingValue"]'))
        review_count = self._parse_count(str(ld.get('aggregateRating', {}).get('reviewCount', '')))

        img_el = (self.soup.select_one('[itemprop="image"]') or
                  self.soup.select_one('img[class*="product"]') or
                  self.soup.select_one('meta[property="og:image"]'))
        if img_el:
            image = self._abs_image(img_el.get('src') or img_el.get('content') or '')
        else:
            image = ''

        reviews = [el.get_text(strip=True) for el in
                   self.soup.select('[class*="review"], [class*="comment"], [class*="yorum"], [itemprop="reviewBody"]')
                   if len(el.get_text(strip=True)) > 30]

        return dict(name=name, brand=brand, price=price, rating=rating,
                    image=image, category='', review_count=review_count, reviews=reviews)

    # ---- Helpers ----

    def _text(self, selector):
        el = self.soup.select_one(selector)
        return el.get_text(strip=True) if el else ''

    def _parse_count(self, text):
        if not text:
            return 0
        m = re.search(r'[\d]+[\d.,]*', text)
        if not m:
            return 0
        try:
            return int(m.group().replace('.', '').replace(',', ''))
        except Exception:
            return 0

    def _name_from_url(self):
        """Ürün adını URL slug'ından çıkar (sayfa erişilemediğinde fallback)."""
        from urllib.parse import urlparse, unquote
        path = unquote(urlparse(self.url).path.strip('/'))
        u = self.url.lower()

        if 'hepsiburada.com' in u:
            m = re.match(r'(.+?)-pm-[A-Z0-9]+$', path)
            slug = m.group(1) if m else path.split('/')[-1]
        elif 'trendyol.com' in u:
            last = path.split('/')[-1]
            m = re.match(r'(.+)-p-\d+', last)
            slug = m.group(1) if m else last
        elif 'amazon.com' in u:
            parts = path.split('/')
            slug = parts[-3] if 'dp' in parts and parts.index('dp') >= 2 else parts[-1]
        elif 'n11.com' in u:
            last = path.split('/')[-1]
            m = re.match(r'(.+)-\d+', last)
            slug = m.group(1) if m else last
        else:
            slug = path.split('/')[-1]

        name = re.sub(r'[-_]+', ' ', slug).strip()
        return ' '.join(w.capitalize() for w in name.split() if w)

    def _validate_image_url(self, url):
        if not url or not url.startswith('http'):
            return False
        from urllib.parse import urlparse
        p = urlparse(url)
        ext = p.path.lower()
        if any(ext.endswith(e) for e in ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif')):
            return True
        cdn_hints = ['cdn.', 'images.', 'productimages.', 'img.', 'static.', 'media.', 'assets.']
        return any(h in p.netloc.lower() for h in cdn_hints)

    def fetch_product_via_search(self):
        """Sayfa erişilemediğinde Gemini + Google Search ile gerçek ürün verisi çek."""
        name = self._name_from_url()
        site = self.detect_site()
        site_map = {'hepsiburada': 'hepsiburada.com', 'trendyol': 'trendyol.com',
                    'amazon': 'amazon.com.tr', 'n11': 'n11.com'}
        site_domain = site_map.get(site, site)

        prompt = (
            f"Bu ürünü {site_domain} sitesinde Google arama sonuçlarından bul:\n"
            f"URL: {self.url}\n"
            f"Tahmini ürün: {name}\n\n"
            "Bulduğun gerçek verileri SADECE şu JSON formatında döndür:\n"
            '{\n'
            '  "name": "<tam ürün adı>",\n'
            '  "brand": "<marka>",\n'
            '  "price": "<güncel TL fiyatı, örnek: 15.499 TL>",\n'
            '  "rating": <5 üzerinden puan>,\n'
            '  "review_count": <yorum sayısı tam sayı>,\n'
            '  "image_url": "<direkt CDN görsel URL, .jpg/.webp/.png uzantılı>",\n'
            '  "category": "<kategori>"\n'
            '}'
        )
        try:
            resp = _genai_client.models.generate_content(
                model=_GEMINI_MODEL,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())]
                )
            )
            text = resp.text.strip()
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
            # JSON bloğunu bul
            m = re.search(r'\{[\s\S]+\}', text)
            data = json.loads(m.group() if m else text)

            image = data.get('image_url', '')
            if not self._validate_image_url(image):
                image = ''

            return {
                'name': data.get('name') or name,
                'brand': data.get('brand', ''),
                'price': data.get('price', ''),
                'rating': float(data.get('rating', 0) or 0),
                'image': image,
                'category': data.get('category', ''),
                'review_count': int(data.get('review_count', 0) or 0),
                'reviews': [],
            }
        except Exception as e:
            print(f"[Search grounding error] {e}")
            return None

    def _extract_trendyol_embedded(self):
        """Trendyol sayfasındaki window['__envoy__SHARED_PROPS'] verisini çeker."""
        if not self.soup:
            return {}
        raw_html = str(self.soup)
        return self._parse_window_prop(raw_html, '__envoy__SHARED_PROPS')

    def _parse_window_prop(self, html_text, key):
        """window["key"] = {...} bloğunu JSON olarak çıkarır."""
        marker = f'window["{key}"]'
        idx = html_text.find(marker)
        if idx == -1:
            return {}
        start = html_text.find('{', idx)
        if start == -1:
            return {}
        raw = html_text[start:]
        depth, end = 0, 0
        for i, ch in enumerate(raw):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        try:
            return json.loads(raw[:end]) if end else {}
        except Exception:
            return {}

    def _get_og_image(self):
        if not self.soup:
            return ''
        for attrs in [{'property': 'og:image'}, {'property': 'og:image:secure_url'}, {'name': 'twitter:image'}]:
            el = self.soup.find('meta', attrs=attrs)
            if el and el.get('content'):
                return el['content']
        link = self.soup.find('link', rel='preload', attrs={'as': 'image'})
        if link and link.get('href'):
            return link['href']
        return ''

    def _get_meta_description(self):
        for attr, name in [('property', 'og:description'), ('name', 'description'),
                           ('name', 'twitter:description')]:
            el = self.soup.select_one(f'meta[{attr}="{name}"]')
            if el and el.get('content'):
                return el['content'][:400]
        return ''

    # ---- Analysis ----

    def analyze_sentiment(self, reviews):
        if not reviews:
            return {'positive': 65, 'neutral': 25, 'negative': 10}
        try:
            sample = reviews[:30]
            reviews_text = "\n".join(f"- {r}" for r in sample)
            prompt = (
                "Aşağıdaki ürün yorumlarını analiz et ve yüzde olarak pozitif, nötr ve negatif dağılımını ver. "
                "Sadece JSON formatında yanıt ver, başka hiçbir şey yazma. Örnek: {\"positive\": 70, \"neutral\": 20, \"negative\": 10}\n\n"
                f"Yorumlar:\n{reviews_text}"
            )
            resp = _genai_client.models.generate_content(model=_GEMINI_MODEL, contents=prompt)
            text = resp.text.strip().strip("```json").strip("```").strip()
            data = json.loads(text)
            pos = max(0, min(100, int(data.get("positive", 65))))
            neg = max(0, min(100, int(data.get("negative", 10))))
            neu = max(0, 100 - pos - neg)
            return {"positive": pos, "neutral": neu, "negative": neg}
        except Exception as e:
            print(f"[Gemini sentiment error] {e}")
            # Fallback: keyword tabanlı
            pos = neg = 0
            for r in reviews:
                rl = r.lower()
                p = sum(1 for w in self.POSITIVE_WORDS if w in rl)
                n = sum(1 for w in self.NEGATIVE_WORDS if w in rl)
                if p > n:
                    pos += 1
                elif n > p:
                    neg += 1
            total = len(reviews)
            positive = round(pos / total * 100)
            negative = round(neg / total * 100)
            neutral = max(0, 100 - positive - negative)
            return {'positive': positive, 'neutral': neutral, 'negative': negative}

    def extract_aspects(self, reviews, aspect_map, max_items=5):
        all_text = ' '.join(reviews).lower()
        found = [aspect for aspect, kws in aspect_map.items() if any(kw in all_text for kw in kws)]
        return found[:max_items]

    def get_audiences(self, product_info, reviews):
        all_text = ' '.join(reviews + [product_info.get('name', ''),
                                       product_info.get('brand', ''),
                                       product_info.get('category', '')]).lower()
        found = [{'name': name, 'icon': icon}
                 for name, (kws, icon) in self.AUDIENCE_MAP.items()
                 if any(kw in all_text for kw in kws)]
        if len(found) < 3:
            defaults = [{'name': 'Genel Kullanım', 'icon': 'people'},
                        {'name': 'Ev Kullanımı', 'icon': 'home'},
                        {'name': 'Profesyoneller', 'icon': 'work'}]
            for d in defaults:
                if not any(f['name'] == d['name'] for f in found):
                    found.append(d)
                if len(found) >= 3:
                    break
        return found[:5]

    def get_recommendation(self, sentiment, rating):
        pos = sentiment.get('positive', 65)
        neg = sentiment.get('negative', 10)
        try:
            prompt = (
                f"Bir e-ticaret ürününün analiz sonuçları: puan={rating}/5, pozitif yorum %{pos}, negatif yorum %{neg}.\n"
                "Bu ürün için aşağıdaki 4 tavsiyeden yalnızca birini seç ve sadece o metni yaz:\n"
                "- Kesinlikle Alınır\n"
                "- Tavsiye Edilir\n"
                "- Değerlendirilebilir\n"
                "- Dikkatli Olunmalı"
            )
            resp = _genai_client.models.generate_content(model=_GEMINI_MODEL, contents=prompt)
            text = resp.text.strip()
            icon_map = {
                'Kesinlikle Alınır': 'task_alt',
                'Tavsiye Edilir': 'check_circle',
                'Değerlendirilebilir': 'lightbulb',
                'Dikkatli Olunmalı': 'priority_high',
            }
            for label, icon in icon_map.items():
                if label in text:
                    return label, icon
        except Exception as e:
            print(f"[Gemini recommendation error] {e}")
        # Fallback
        if pos >= 75 or (rating and rating >= 4.5):
            return 'Kesinlikle Alınır', 'thumb_up'
        if pos >= 60 or (rating and rating >= 4.0):
            return 'Tavsiye Edilir', 'recommend'
        if pos >= 45:
            return 'Değerlendirilebilir', 'lightbulb'
        return 'Dikkatli Olunmalı', 'warning'

    def get_trust_score(self, reviews, review_count):
        score = 65
        if reviews:
            avg_len = sum(len(r) for r in reviews) / len(reviews)
            if avg_len > 100:
                score += 18
            elif avg_len > 50:
                score += 10
        if review_count > 1000:
            score += 12
        elif review_count > 200:
            score += 6
        elif review_count > 50:
            score += 3
        return min(score, 98)

    def get_trend(self, sentiment=None):
        months = ['Oca', 'Şub', 'Mar', 'Nis', 'May']
        if sentiment:
            target = max(20, min(90, sentiment.get('positive', 60)))
            v = max(20, target - random.randint(15, 28))
            values = []
            for _ in range(4):
                v = max(20, min(90, v + random.randint(-6, 12)))
                values.append(v)
            values.append(max(20, min(95, target + random.randint(-3, 5))))
        else:
            base = random.randint(40, 65)
            values = [max(20, base + random.randint(-15, 15)) for _ in range(4)]
            values.append(random.randint(70, 95))
        return {'months': months, 'values': values}

    def gemini_analyze(self, product_info, reviews, description):
        name = product_info.get('name', '')
        brand = product_info.get('brand', '')
        price = product_info.get('price', '')
        rating = product_info.get('rating', 0)
        review_count = product_info.get('review_count', 0)
        category = product_info.get('category', '')

        context_lines = [f"Ürün: {(brand + ' ' + name).strip()}"]
        if category:
            context_lines.append(f"Kategori: {category}")
        if price:
            context_lines.append(f"Fiyat: {price}")
        if rating:
            context_lines.append(f"Puan: {rating}/5")
        if review_count:
            context_lines.append(f"Toplam yorum sayısı: {review_count}")
        if description:
            context_lines.append(f"Açıklama: {description}")

        review_section = ""
        if reviews:
            review_text = "\n".join(f"- {r}" for r in reviews[:25])
            review_section = f"\n\nKullanıcı Yorumları:\n{review_text}"

        lang_inst = LANG_PROMPTS.get(self.lang, LANG_PROMPTS['tr'])

        prompt = (
            lang_inst + "\n\n" +
            "\n".join(context_lines) + review_section +
            "\n\nBu ürüne özel kapsamlı bir analiz yap. SADECE aşağıdaki JSON formatında yanıt ver, başka hiçbir şey ekleme:\n"
            '{\n'
            '  "sentiment": {"positive": <0-100 tam sayı>, "neutral": <0-100 tam sayı>, "negative": <0-100 tam sayı>},\n'
            '  "positives": ["<bu ürüne özel olumlu özellik>", "<olumlu özellik>", "<olumlu özellik>"],\n'
            '  "negatives": ["<bu ürüne özel olumsuz özellik>", "<olumsuz özellik>"],\n'
            '  "summary": "<bu ürüne özel 2-3 cümlelik doğal Türkçe özet>",\n'
            '  "recommendation": "<tam olarak şunlardan biri: Kesinlikle Alınır | Tavsiye Edilir | Değerlendirilebilir | Dikkatli Olunmalı>",\n'
            '  "audiences": [{"name": "<hedef kitle>", "icon": "<material icon ismi>"}, {"name": "...", "icon": "..."}, {"name": "...", "icon": "..."}],\n'
            '  "price_estimate": "<bu ürünün Türkiye piyasasındaki tahmini fiyat aralığı, örnek: 8.500 - 12.000 TL>",\n'
            '  "review_count_estimate": <bu ürünün büyük e-ticaret sitelerinde sahip olduğu tahmini toplam yorum sayısı, tam sayı>\n'
            '}'
        )

        resp = _genai_client.models.generate_content(model=_GEMINI_MODEL, contents=prompt)
        text = resp.text.strip()
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        data = json.loads(text)

        s = data.get('sentiment', {})
        pos = max(0, min(100, int(s.get('positive', 65))))
        neg = max(0, min(100, int(s.get('negative', 10))))
        neu = max(0, 100 - pos - neg)

        icon_map = {
            'Kesinlikle Alınır': 'task_alt',
            'Tavsiye Edilir': 'check_circle',
            'Değerlendirilebilir': 'lightbulb',
            'Dikkatli Olunmalı': 'priority_high',
        }
        rec = data.get('recommendation', 'Değerlendirilebilir')
        rec_icon = next((v for k, v in icon_map.items() if k in rec), 'lightbulb')
        rec = next((k for k in icon_map if k in rec), 'Değerlendirilebilir')

        return {
            'sentiment': {'positive': pos, 'neutral': neu, 'negative': neg},
            'positives': [p for p in data.get('positives', []) if p][:5],
            'negatives': [n for n in data.get('negatives', []) if n][:5],
            'summary': data.get('summary', ''),
            'recommendation': rec,
            'recommendation_icon': rec_icon,
            'audiences': data.get('audiences', [])[:5],
            'price_estimate': str(data.get('price_estimate', '') or ''),
            'review_count_estimate': int(data.get('review_count_estimate', 0) or 0),
        }

    def generate_summary(self, product_info, sentiment, positives, negatives):
        name = product_info.get('name', 'Bu ürün')
        brand = product_info.get('brand', '')
        review_count = product_info.get('review_count', 0)
        full_name = f"{brand} {name}".strip() if brand else name
        try:
            prompt = (
                f"'{full_name}' adlı ürün için {review_count} yorum analiz edildi.\n"
                f"Duygu dağılımı: %{sentiment.get('positive', 65)} pozitif, %{sentiment.get('neutral', 25)} nötr, %{sentiment.get('negative', 10)} negatif.\n"
                f"Olumlu yönler: {', '.join(positives[:3]) if positives else 'belirsiz'}.\n"
                f"Olumsuz yönler: {', '.join(negatives[:2]) if negatives else 'belirsiz'}.\n\n"
                "Bu bilgilere göre ürün için doğal ve akıcı Türkçe ile 2-3 cümlelik bir özet yaz. "
                "Sadece özeti yaz, başlık veya açıklama ekleme."
            )
            resp = _genai_client.models.generate_content(model=_GEMINI_MODEL, contents=prompt)
            return resp.text.strip()
        except Exception as e:
            print(f"[Gemini summary error] {e}")
            # Fallback: template tabanlı
            pos_pct = sentiment.get('positive', 65)
            count_str = f"{review_count} yorum" if review_count > 0 else "mevcut yorumlar"
            if pos_pct >= 75:
                verdict = f"kullanıcıların %{pos_pct}'i üründen memnun"
            elif pos_pct >= 55:
                verdict = f"kullanıcı görüşleri genel olarak olumlu (%{pos_pct} pozitif)"
            elif pos_pct >= 40:
                verdict = f"yorumlar karışık (%{pos_pct} olumlu, %{sentiment.get('negative', 0)} olumsuz)"
            else:
                verdict = f"kullanıcıların büyük çoğunluğu üründen memnun değil (%{sentiment.get('negative', 0)} negatif)"
            summary = f"{full_name} için {count_str} analiz edildi; {verdict}."
            if positives:
                summary += f" Öne çıkan olumlu yönler: {', '.join(positives[:2])}."
            if negatives:
                summary += f" En çok şikayet edilen konular: {', '.join(negatives[:1])}."
            return summary

    def analyze(self):
        page_fetched = self.fetch_page()
        site = self.detect_site()

        if page_fetched:
            extractors = {
                'trendyol': self.extract_trendyol,
                'hepsiburada': self.extract_hepsiburada,
                'amazon': self.extract_amazon,
                'n11': self.extract_n11,
                'generic': self.extract_generic,
            }
            product_info = extractors.get(site, self.extract_generic)()

            if not product_info.get('name') or product_info['name'] in ('Ürün', ''):
                generic = self.extract_generic()
                product_info['name'] = generic.get('name', self._name_from_url())

            if not product_info.get('image'):
                product_info['image'] = self._get_og_image()

            description = self._get_meta_description()
        else:
            # Sayfa erişilemedi — önce Gemini Search Grounding ile gerçek veri çek
            print(f"[Fetch failed] Search grounding deneniyor: {self.url}")
            search_result = self.fetch_product_via_search()
            if search_result and search_result.get('name'):
                product_info = search_result
                print(f"[Search grounding OK] {product_info['name']} | fiyat={product_info.get('price')} | görsel={bool(product_info.get('image'))}")
            else:
                # Son fallback: URL slug parse
                print(f"[Search grounding failed] URL parse fallback: {self.url}")
                product_info = {
                    'name': self._name_from_url(),
                    'brand': '', 'price': '', 'rating': 0,
                    'image': '', 'category': '', 'review_count': 0,
                }
            description = ''

        reviews = product_info.pop('reviews', [])
        review_count = product_info.get('review_count', len(reviews))
        if review_count == 0 and reviews:
            review_count = len(reviews)
            product_info['review_count'] = review_count

        price_estimated = False
        review_count_estimated = False

        # Single comprehensive Gemini call — product-specific even without reviews
        try:
            ai = self.gemini_analyze(product_info, reviews, description)
            sentiment = ai['sentiment']
            positives = ai['positives']
            negatives = ai['negatives']
            summary = ai['summary']
            recommendation = ai['recommendation']
            rec_icon = ai['recommendation_icon']
            audiences = ai['audiences']

            # Fill in missing price from Gemini estimate
            if not product_info.get('price') and ai.get('price_estimate'):
                product_info['price'] = ai['price_estimate']
                price_estimated = True

            # Fill in missing review count from Gemini estimate
            if review_count == 0 and ai.get('review_count_estimate', 0) > 0:
                review_count = ai['review_count_estimate']
                product_info['review_count'] = review_count
                review_count_estimated = True

        except Exception as e:
            print(f"[Gemini full analysis error] {e}")
            sentiment = self.analyze_sentiment(reviews)
            positives = self.extract_aspects(reviews, self.POSITIVE_ASPECTS)
            negatives = self.extract_aspects(reviews, self.NEGATIVE_ASPECTS)
            if not positives:
                positives = (['Genel kullanıcı memnuniyeti yüksek', 'Ürün beklentileri karşılıyor']
                             if sentiment['positive'] > 55 else ['Bazı kullanıcılar üründen memnun'])
            if not negatives:
                negatives = (['Belirgin şikayet kategorisi tespit edilmedi']
                             if sentiment['negative'] < 25 else ['Bazı kullanıcılar sorun yaşamış'])
            recommendation, rec_icon = self.get_recommendation(sentiment, product_info.get('rating', 0))
            summary = self.generate_summary(product_info, sentiment, positives, negatives)
            audiences = self.get_audiences(product_info, reviews)

        product_info['price_estimated'] = price_estimated

        trust_score = self.get_trust_score(reviews, review_count)

        # Risk seviyesi hesapla
        if trust_score >= 85:
            risk_label, risk_icon, risk_color = 'Düşük Risk', 'verified', 'text-primary-container'
        elif trust_score >= 70:
            risk_label, risk_icon, risk_color = 'Orta Risk', 'info', 'text-secondary'
        else:
            risk_label, risk_icon, risk_color = 'Yüksek Risk', 'warning', 'text-error'

        return {
            'product': product_info,
            'recommendation': recommendation,
            'recommendation_icon': rec_icon,
            'positives': positives,
            'negatives': negatives,
            'audiences': audiences,
            'sentiment': sentiment,
            'trust_score': trust_score,
            'risk_label': risk_label,
            'risk_icon': risk_icon,
            'risk_color': risk_color,
            'review_count': review_count,
            'review_count_estimated': review_count_estimated,
            'page_accessible': page_fetched,
            'summary': summary,
            'url': self.url,
            'site': site,
        }


# ============================================================
# ROUTES
# ============================================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['GET', 'POST'])
def analyze_route():
    if request.method == 'GET':
        return render_template('index.html')

    data = request.get_json(silent=True) or {}
    url = (data.get('url') or '').strip()
    lang = (data.get('lang') or 'tr').strip()
    if lang not in LANG_PROMPTS:
        lang = 'tr'
    if not url:
        return jsonify({'error': 'URL gerekli'}), 400
    if not (url.startswith('http://') or url.startswith('https://')):
        url = 'https://' + url

    session['lang'] = lang
    analyzer = RealAnalyzer(url, lang=lang)
    result = analyzer.analyze()

    if result is None:
        return jsonify({'error': 'Ürün sayfasına erişilemedi. Lütfen geçerli bir ürün linki girin.'}), 422

    session['last_analysis'] = result
    return jsonify({'success': True, 'redirect': '/results'})

@app.route('/results')
def results():
    analysis = session.get('last_analysis')
    if not analysis:
        return render_template('index.html')
    return render_template('results.html', data=analysis)

@app.route('/loading')
def loading():
    return render_template('loading.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/api/results')
def api_results():
    analysis = session.get('last_analysis')
    if not analysis:
        return jsonify({'error': 'Analiz bulunamadı'}), 404
    return jsonify(analysis)

# ----- Auth -----
 

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not name or not email or not password:
        return jsonify({'error': 'Tüm alanlar zorunludur'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Şifre en az 6 karakter olmalıdır'}), 400
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return jsonify({'error': 'Geçerli bir e-posta girin'}), 400

    users = load_users()
    if email in users:
        return jsonify({'error': 'Bu e-posta adresi zaten kayıtlı'}), 409

    users[email] = {
        'name': name,
        'email': email,
        'password': hash_password(password),
        'created_at': datetime.now().isoformat(),
    }
    save_users(users)
    session['user'] = {'name': name, 'email': email}
    return jsonify({'success': True, 'name': name})

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({'error': 'E-posta ve şifre gereklidir'}), 400

    users = load_users()
    user = users.get(email)
    if not user or user['password'] != hash_password(password):
        return jsonify({'error': 'E-posta veya şifre hatalı'}), 401

    session['user'] = {'name': user['name'], 'email': email}
    return jsonify({'success': True, 'name': user['name']})

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
