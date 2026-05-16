from flask import Flask, render_template, request, jsonify, session
import requests
from bs4 import BeautifulSoup
import re
import random
import time
from datetime import datetime

app = Flask(__name__)
app.secret_key = "shopmind-ai-secret-key-2024"

# ============================================================
# MOCK DATA GENERATOR (Gerçek API yerine demo veri)
# ============================================================
class MockAnalyzer:
    def __init__(self, url):
        self.url = url
        self.product_types = [
            {"name": "Sony WH-1000XM5", "brand": "Sony", "price": "₺8.499", "rating": 4.7, "image": "https://images.unsplash.com/photo-1618366712010-f4ae9c647dcb?w=400", "category": "Kulaklık"},
            {"name": "iPhone 15 Pro Max", "brand": "Apple", "price": "₺74.999", "rating": 4.8, "image": "https://images.unsplash.com/photo-1696446701796-da61225697cc?w=400", "category": "Telefon"},
            {"name": "Samsung Galaxy S24 Ultra", "brand": "Samsung", "price": "₺52.999", "rating": 4.6, "image": "https://images.unsplash.com/photo-1610945265078-3858a0828671?w=400", "category": "Telefon"},
            {"name": "MacBook Air M3", "brand": "Apple", "price": "₺42.999", "rating": 4.9, "image": "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=400", "category": "Laptop"},
            {"name": "Dyson V15 Detect", "brand": "Dyson", "price": "₺24.999", "rating": 4.5, "image": "https://images.unsplash.com/photo-1558317374-067fb5f30001?w=400", "category": "Ev Aleti"},
            {"name": "Nike Air Max 90", "brand": "Nike", "price": "₺3.299", "rating": 4.4, "image": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400", "category": "Ayakkabı"},
            {"name": "Logitech MX Master 3S", "brand": "Logitech", "price": "₺2.899", "rating": 4.8, "image": "https://images.unsplash.com/photo-1527864550417-7fd91fc51a46?w=400", "category": "Aksesuar"},
            {"name": "Philips Airfryer XXL", "brand": "Philips", "price": "₺4.599", "rating": 4.6, "image": "https://images.unsplash.com/photo-1626147116986-4601771470a6?w=400", "category": "Mutfak"},
        ]

        # URL hash'ine göre tutarlı ürün seç
        url_hash = sum(ord(c) for c in url) % len(self.product_types)
        self.product = self.product_types[url_hash]

        self.positives = [
            "Kusursuz performans ve hızlı tepki süresi",
            "Premium malzeme kalitesi ve dayanıklılık",
            "Kullanıcı dostu arayüz ve kolay kurulum",
            "Uzun pil ömrü ve hızlı şarj özelliği",
            "Mükemmel ses/görüntü kalitesi",
            "Ergonomik tasarım ve konforlu kullanım",
            "Çoklu cihaz bağlantısı ve uyumluluk",
            "Gelişmiş özellikler ve kişiselleştirme",
        ]

        self.negatives = [
            "Fiyat/performans oranı biraz yüksek",
            "Orijinal aksesuarlar pahalı",
            "Yazılım güncellemeleri ara sıra sorunlu",
            "Aşırı ısınma uzun kullanımda hissediliyor",
            "Tasarım biraz ağır/büyük gelebilir",
            "Müşteri hizmetleri yanıt süresi uzun",
            "Ambalajlama ve kargo kalitesi düşük",
            "Bazı özellikler sadece premium modellerde",
        ]

        self.audiences = [
            {"name": "Profesyoneller", "icon": "work"},
            {"name": "Öğrenciler", "icon": "school"},
            {"name": "Oyuncular", "icon": "sports_esports"},
            {"name": "Gezginler", "icon": "flight"},
            {"name": "Ev Hanımları", "icon": "home"},
            {"name": "Sporcular", "icon": "fitness_center"},
            {"name": "Teknoloji Tutkunları", "icon": "devices"},
            {"name": "Tasarımcılar", "icon": "palette"},
        ]

        self.recommendations = ["Kesinlikle Alınır", "Tavsiye Edilir", "Değerlendirilebilir", "Düşünülebilir"]
        self.recommendation_icons = ["thumb_up", "recommend", "lightbulb", "help"]

    def analyze(self):
        # Tutarlı rastgele değerler
        random.seed(sum(ord(c) for c in self.url))

        positive_count = random.randint(3, 5)
        negative_count = random.randint(2, 4)

        selected_positives = random.sample(self.positives, positive_count)
        selected_negatives = random.sample(self.negatives, negative_count)

        audience_count = random.randint(3, 5)
        selected_audiences = random.sample(self.audiences, audience_count)

        rec_index = random.randint(0, 3)

        sentiment = {
            "positive": random.randint(70, 90),
            "neutral": random.randint(5, 20),
            "negative": random.randint(2, 15)
        }
        # Normalize to 100
        total = sum(sentiment.values())
        sentiment = {k: round(v/total*100) for k, v in sentiment.items()}

        trust_score = random.randint(85, 98)
        review_count = random.randint(500, 5000)

        # Trend data (last 5 months)
        months = ["Oca", "Şub", "Mar", "Nis", "May"]
        trend = [random.randint(40, 70) for _ in range(4)]
        trend.append(random.randint(75, 95))  # Current month higher

        summary = self._generate_summary()

        return {
            "product": self.product,
            "recommendation": self.recommendations[rec_index],
            "recommendation_icon": self.recommendation_icons[rec_index],
            "positives": selected_positives,
            "negatives": selected_negatives,
            "audiences": selected_audiences,
            "sentiment": sentiment,
            "trust_score": trust_score,
            "review_count": review_count,
            "trend": {"months": months, "values": trend},
            "summary": summary,
            "url": self.url
        }

    def _generate_summary(self):
        summaries = [
            f"Kullanıcı yorumlarının %{random.randint(75,90)}'i {self.product['brand']} {self.product['name']} ürününden son derece memnun. Genel yapı kalitesi premium hissettiriyor ve fiyat segmentine göre beklentileri karşılıyor.",
            f"{self.product['brand']} {self.product['name']} için yapılan {random.randint(1000,3000)} yorumun büyük çoğunluğu olumlu. Ürünün en çok övülen yönleri performans ve tasarım.",
            f"{self.product['category']} kategorisinde {self.product['brand']} {self.product['name']} kullanıcıları tarafından %{random.randint(80,95)} oranında tavsiye ediliyor. Pil ömrü ve bağlantı kalitesi en çok beğenilen özellikler.",
        ]
        return random.choice(summaries)


# ============================================================
# ROUTES
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    url = data.get("url", "")

    if not url:
        return jsonify({"error": "URL gerekli"}), 400

    # URL doğrulama
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url

    # Demo modda mock analiz yap
    analyzer = MockAnalyzer(url)
    result = analyzer.analyze()

    # Session'a kaydet
    session["last_analysis"] = result

    return jsonify({"success": True, "redirect": "/results"})

@app.route("/results")
def results():
    analysis = session.get("last_analysis")
    if not analysis:
        return render_template("index.html")
    return render_template("results.html", data=analysis)

@app.route("/loading")
def loading():
    return render_template("loading.html")

@app.route("/api/results")
def api_results():
    analysis = session.get("last_analysis")
    if not analysis:
        return jsonify({"error": "Analiz bulunamadı"}), 404
    return jsonify(analysis)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)