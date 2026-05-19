<div align="center">

# 🛍️ ShopMind AI

### Yapay Zekâ Destekli Ürün Analiz Platformu

*Bir link yapıştır — satın alma kararını yapay zekâya bırak.*

<br/>

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![Gemini AI](https://img.shields.io/badge/Gemini-2.5_Flash-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

</div>

---

## 📖 Proje Hakkında

**ShopMind AI**, kullanıcıların e-ticaret sitelerindeki ürün linklerini yapıştırarak saniyeler içinde yapay zekâ destekli derin bir analiz elde etmesini sağlayan bir karar destek platformudur.

Trendyol, Hepsiburada ve Amazon gibi büyük platformlardan alınan ürün sayfaları otomatik olarak taranır; kullanıcı yorumları, puanlar ve ürün bilgileri **Google Gemini AI** aracılığıyla işlenerek anlamlı içgörülere dönüştürülür. Sistem; satın alma tavsiyesi, artı/eksi analizi, duygu skoru, sahte yorum risk tespiti ve hedef kitle önerileri sunar.

> Amacımız tek: tüketicilerin daha bilinçli ve hızlı alışveriş kararları almasına yardımcı olmak.

---

## ✨ Özellikler

| Özellik | Açıklama |
|---|---|
| 🤖 **AI Karar Motoru** | "Kesinlikle Alınır" → "Dikkatli Olunmalı" arasında 4 kademeli satın alma tavsiyesi |
| 📊 **Duygu Analizi** | Yorumları pozitif / nötr / negatif olarak sınıflandırır, yüzdesel dağılım gösterir |
| ✅ **Artılar & Eksiler** | Yüzlerce yorumdan en sık geçen olumlu ve olumsuz özellikleri özet olarak çıkarır |
| 🛡️ **Sahte Yorum Tespiti** | Güven skoru ile sahte yorum riskini görsel olarak ortaya koyar |
| 🎯 **Hedef Kitle Analizi** | Ürünün hangi kullanıcı profilleri için uygun olduğunu belirler |
| 🌐 **Çoklu Platform** | Trendyol, Hepsiburada, Amazon ve N11 desteği |
| 🔐 **Kullanıcı Sistemi** | Kayıt, giriş ve oturum yönetimi |
| 🐳 **Docker Desteği** | Tek komutla production ortamında ayağa kaldırma |

---

## 🛠️ Teknoloji Yığını

```
Backend        →  Python 3.11 · Flask 3.0 · Requests · BeautifulSoup4
AI / NLP       →  Google Gemini 2.5 Flash (analiz + arama tabanlı grounding)
Scraping       →  Multi-layer fallback: REST API → Embedded JSON → JSON-LD → HTML → Playwright → AI
Frontend       →  Jinja2 · Tailwind CSS · Material Symbols · Vanilla JS
Altyapı        →  Docker · Docker Compose
```

---

## 🚀 Kurulum

### Ön Gereksinimler

- Python **3.11+**
- pip
- Google Gemini API anahtarı → [Ücretsiz al](https://aistudio.google.com/app/apikey)
- *(Opsiyonel)* Docker & Docker Compose

---

### 1. Yerel Kurulum

```bash
# Proje klasörüne gir
cd shopmind-ai

# Sanal ortam oluştur ve aktifleştir
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# Bağımlılıkları yükle
pip install -r requirements.txt
```

API anahtarını ortam değişkeni olarak tanımla:

```bash
# Windows (PowerShell)
$env:GEMINI_API_KEY="buraya_api_anahtarinizi_girin"

# macOS / Linux
export GEMINI_API_KEY="buraya_api_anahtarinizi_girin"
```

Uygulamayı başlat:

```bash
python app.py
```

Tarayıcınızda `http://localhost:5000` adresine gidin.

---

### 2. Docker ile Kurulum

`docker-compose.yml` dosyasındaki `GEMINI_API_KEY` satırını kendi anahtarınızla doldurun:

```yaml
environment:
  - GEMINI_API_KEY=buraya_api_anahtarinizi_girin
```

Ardından:

```bash
# İmajı oluştur ve başlat
docker compose up --build -d

# Logları takip et
docker compose logs -f

# Durdurmak için
docker compose down
```

Uygulama `http://localhost:5000` adresinde erişilebilir hale gelir.

---

### 3. Ortam Değişkenleri

| Değişken | Açıklama | Zorunlu |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini API anahtarı | ✅ Evet |
| `FLASK_SECRET_KEY` | Flask oturum şifreleme anahtarı | Önerilir |

> **İpucu:** Production ortamında `FLASK_SECRET_KEY` için güçlü, rastgele bir değer kullanın:
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

---

### 4. Playwright Desteği *(Opsiyonel)*

Bot koruması aktif olan sayfalarda JavaScript render desteği için:

```bash
pip install playwright
playwright install chromium
```

Playwright kuruluysa, HTML scraping başarısız olduğunda otomatik olarak devreye girer.

---

## 📁 Proje Yapısı

```
shopmind-ai/
├── app.py                  # Ana backend: scraping + AI analiz + Flask rotaları
├── requirements.txt        # Python bağımlılıkları
├── Dockerfile              # Docker imaj tanımı
├── docker-compose.yml      # Docker Compose konfigürasyonu
├── users.json              # Kullanıcı veritabanı (otomatik oluşturulur)
└── templates/
    ├── base.html           # Ana şablon (navigasyon, tema, genel layout)
    ├── index.html          # Ana sayfa (URL girişi)
    ├── loading.html        # Analiz yükleme ekranı (canlı durum mesajları)
    ├── results.html        # Analiz sonuç sayfası
    └── about.html          # Hakkında sayfası
```

---

## 📸 Ekran Görüntüleri

> *Ekran görüntüleri yakında eklenecektir.*

| Ana Sayfa | Yükleme | Sonuçlar |
|---|---|---|
| *(screenshot)* | *(screenshot)* | *(screenshot)* |

---

## 🔄 Nasıl Çalışır?

```
Kullanıcı bir ürün linki girer
        ↓
Site tespit edilir (Trendyol / Hepsiburada / Amazon / ...)
        ↓
Çok katmanlı scraping fallback zinciri çalışır:
   1. Platform REST API'si (varsa)
   2. Sayfadaki gömülü JSON verisi (__NEXT_DATA__, window.* props)
   3. JSON-LD yapılandırılmış veri
   4. HTML CSS seçicileri
   5. Playwright ile headless browser render (opsiyonel)
   6. Gemini AI arama tabanlı veri çekme (son yedek)
        ↓
Yorumlar + ürün bilgisi Gemini 2.5 Flash'a gönderilir
        ↓
AI: duygu analizi · artılar/eksiler · satın alma tavsiyesi · hedef kitle üretir
        ↓
Sonuçlar görsel dashboard'da sunulur
```

---

## ⚠️ Bilinen Kısıtlamalar & Yol Haritası

### Mevcut Kısıtlamalar

Trendyol, Hepsiburada ve Amazon gibi büyük e-ticaret platformları, bot ve otomatik erişim sistemlerine karşı güçlü güvenlik katmanları (Akamai Bot Manager, Cloudflare vb.) kullanmaktadır. Bu durum zaman zaman ürün görsellerinin veya yorum verilerinin çekilmesini engelleyebilir.

ShopMind AI bu engeli aşmak için **çok katmanlı bir fallback zinciri** kullanır ve başarısız istekleri yeniden dener. Belirli zaman dilimlerinde platforma erişildiğinde analizin tüm katmanları eksiksiz biçimde çalışmaktadır.

> **Köklü çözüm:** Söz konusu platformların resmi API erişimi sağlaması ya da veri ortaklıkları kurması durumunda bu kısıtlamalar tamamen ortadan kalkacak; çok daha hızlı, eksiksiz ve güvenilir analizler sunmak mümkün olacaktır.

### Yol Haritası

- [ ] Resmi platform API entegrasyonları (Trendyol Partner API, Amazon PA-API vb.)
- [ ] Analiz geçmişi ve karşılaştırma özelliği
- [ ] Fiyat takibi ve bildirim sistemi
- [ ] Ürünler arası karşılaştırma modülü
- [ ] Tarayıcı eklentisi (Chrome / Firefox)
- [ ] Toplu analiz (birden fazla ürün aynı anda)
- [ ] Export: PDF raporu / CSV çıktısı

---

## 🤝 Katkıda Bulunma

Katkılarınız projeyi daha iyi hale getirir. Her türlü katkı kabul edilir:

1. Repoyu **fork**'layın
2. Özellik dalı oluşturun: `git checkout -b feature/yeni-ozellik`
3. Değişikliklerinizi commit edin: `git commit -m 'feat: yeni özellik eklendi'`
4. Dalınızı push edin: `git push origin feature/yeni-ozellik`
5. **Pull Request** açın

---

## 📄 Lisans

Bu proje **MIT Lisansı** altında dağıtılmaktadır.

---

<div align="center">

**ShopMind AI** · *Akıllı alışveriş kararları için*

</div>
