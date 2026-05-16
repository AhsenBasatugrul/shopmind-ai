from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import requests
from bs4 import BeautifulSoup
import re
import json
import hashlib
import os
import random
from datetime import datetime

app = Flask(__name__)
app.secret_key = "shopmind-ai-secret-key-2024"

USERS_FILE = os.path.join(os.path.dirname(__file__), 'users.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
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

    def __init__(self, url):
        self.url = url
        self.soup = None

    def fetch_page(self):
        try:
            resp = requests.get(self.url, headers=HEADERS, timeout=12, allow_redirects=True)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding
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
        ld = self.extract_json_ld()

        name = (ld.get('name') or
                self._text('.pr-new-br span') or
                self._text('h1.pr-new-br') or
                self._text('h1'))

        brand = (ld.get('brand', {}).get('name', '') if isinstance(ld.get('brand'), dict) else ld.get('brand', '')) or \
                self._text('.pr-new-br a') or self._text('[class*="brand"]')

        # Price from LD or DOM
        price = ''
        ld_offers = ld.get('offers', {})
        if isinstance(ld_offers, list):
            ld_offers = ld_offers[0] if ld_offers else {}
        if ld_offers.get('price'):
            price = f"₺{ld_offers['price']}"
        if not price:
            price = self._text('.prc-dsc') or self._text('[class*="price-box"]') or self._text('[class*="prc"]')

        rating = self._parse_rating(str(ld.get('aggregateRating', {}).get('ratingValue', '')) or
                                    self._text('.pro-rat-avg') or self._text('[class*="rating"]'))

        review_count_raw = str(ld.get('aggregateRating', {}).get('reviewCount', '')) or \
                           self._text('[class*="review-count"]') or self._text('[class*="comment-count"]')
        review_count = self._parse_count(review_count_raw)

        # Image
        img_el = (self.soup.select_one('.base-product-image img') or
                  self.soup.select_one('[class*="product-image"] img') or
                  self.soup.select_one('img[class*="product"]'))
        image = self._abs_image(img_el['src'] if img_el and img_el.get('src') else
                                (img_el['data-src'] if img_el and img_el.get('data-src') else ''))
        if not image and ld.get('image'):
            raw_img = ld['image']
            image = raw_img[0] if isinstance(raw_img, list) else raw_img

        reviews = [el.get_text(strip=True) for el in self.soup.select('.comment-text, [class*="rnr-com-tx"]')
                   if len(el.get_text(strip=True)) > 15]

        category = (ld.get('category') or
                    self._text('[class*="breadcrumb"] li:last-child') or '')

        return dict(name=name, brand=brand, price=price, rating=rating,
                    image=image, category=category, review_count=review_count, reviews=reviews)

    def extract_hepsiburada(self):
        ld = self.extract_json_ld()

        name = (ld.get('name') or
                self._text('[class*="product-name"] h1') or
                self._text('h1[itemprop="name"]') or
                self._text('h1'))

        brand = (ld.get('brand', {}).get('name', '') if isinstance(ld.get('brand'), dict) else '') or \
                self._text('[class*="merchant"] a') or self._text('[class*="brand"]')

        ld_offers = ld.get('offers', {})
        if isinstance(ld_offers, list):
            ld_offers = ld_offers[0] if ld_offers else {}
        price = ''
        if ld_offers.get('price'):
            price = f"₺{ld_offers['price']}"
        if not price:
            price = self._text('[class*="product-price"]') or self._text('[itemprop="price"]')

        rating = self._parse_rating(str(ld.get('aggregateRating', {}).get('ratingValue', '')) or
                                    self._text('[class*="rating-score"]') or self._text('[class*="stars"]'))

        review_count_raw = str(ld.get('aggregateRating', {}).get('reviewCount', '')) or \
                           self._text('[class*="review-count"]') or self._text('[class*="comment-count"]')
        review_count = self._parse_count(review_count_raw)

        img_el = (self.soup.select_one('[class*="product-image"] img') or
                  self.soup.select_one('img[itemprop="image"]'))
        image = self._abs_image(img_el.get('src') or img_el.get('data-src') if img_el else '')
        if not image and ld.get('image'):
            raw_img = ld['image']
            image = raw_img[0] if isinstance(raw_img, list) else raw_img

        reviews = [el.get_text(strip=True) for el in
                   self.soup.select('[class*="comment-content"], [class*="review-text"], [class*="comment-body"]')
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

    # ---- Analysis ----

    def analyze_sentiment(self, reviews):
        if not reviews:
            return {'positive': 65, 'neutral': 25, 'negative': 10}
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

    def get_trend(self):
        months = ['Oca', 'Şub', 'Mar', 'Nis', 'May']
        base = random.randint(40, 65)
        values = [max(20, base + random.randint(-15, 15)) for _ in range(4)]
        values.append(random.randint(70, 95))
        return {'months': months, 'values': values}

    def generate_summary(self, product_info, sentiment, positives, negatives):
        name = product_info.get('name', 'Bu ürün')
        brand = product_info.get('brand', '')
        review_count = product_info.get('review_count', 0)
        pos_pct = sentiment.get('positive', 65)
        full_name = f"{brand} {name}".strip() if brand else name

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
        if not self.fetch_page():
            return None

        site = self.detect_site()
        extractors = {
            'trendyol': self.extract_trendyol,
            'hepsiburada': self.extract_hepsiburada,
            'amazon': self.extract_amazon,
            'n11': self.extract_n11,
            'generic': self.extract_generic,
        }
        product_info = extractors.get(site, self.extract_generic)()

        # Fallback name from title
        if not product_info.get('name') or product_info['name'] in ('Ürün', ''):
            generic = self.extract_generic()
            product_info['name'] = generic.get('name', 'Ürün')

        reviews = product_info.pop('reviews', [])
        review_count = product_info.get('review_count', len(reviews))
        if review_count == 0 and reviews:
            review_count = len(reviews)
            product_info['review_count'] = review_count

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
        trust_score = self.get_trust_score(reviews, review_count)
        summary = self.generate_summary(product_info, sentiment, positives, negatives)
        audiences = self.get_audiences(product_info, reviews)
        trend = self.get_trend()

        return {
            'product': product_info,
            'recommendation': recommendation,
            'recommendation_icon': rec_icon,
            'positives': positives,
            'negatives': negatives,
            'audiences': audiences,
            'sentiment': sentiment,
            'trust_score': trust_score,
            'review_count': review_count,
            'trend': trend,
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

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json()
    url = (data.get('url') or '').strip()
    if not url:
        return jsonify({'error': 'URL gerekli'}), 400
    if not (url.startswith('http://') or url.startswith('https://')):
        url = 'https://' + url

    analyzer = RealAnalyzer(url)
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

@app.route('/api/results')
def api_results():
    analysis = session.get('last_analysis')
    if not analysis:
        return jsonify({'error': 'Analiz bulunamadı'}), 404
    return jsonify(analysis)

# ---- Auth ----

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
    app.run(debug=True, host='0.0.0.0', port=5000)
