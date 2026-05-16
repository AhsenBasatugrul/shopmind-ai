# ShopMind AI - Akıllı Ürün Analizi Platformu

## 🚀 Hızlı Başlangıç

### Gereksinimler
- Python 3.8+
- pip

### Kurulum

```bash
# 1. Projeyi klasöre çıkarın
cd shopmind-ai

# 2. Sanal ortam oluşturun (opsiyonel ama önerilir)
python -m venv venv

# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 3. Bağımlılıkları yükleyin
pip install -r requirements.txt

# 4. Uygulamayı çalıştırın
python app.py
```

### Kullanım

Tarayıcınızda `http://localhost:5000` adresine gidin.

1. **Ana Sayfa**: Herhangi bir e-ticaret sitesi linkini yapıştırın
2. **Yükleme Ekranı**: AI analiz ederken animasyonlu bekleme ekranı
3. **Sonuçlar**: 
   - Ürün bilgileri
   - AI kararı (Kesinlikle Alınır / Tavsiye Edilir vb.)
   - Artılar & Eksiler
   - Duygu analizi (Pozitif/Nötr/Negatif)
   - Sahte yorum risk skoru
   - Memnuniyet trendi
   - Hedef kitle önerileri

## 📁 Proje Yapısı

```
shopmind-ai/
├── app.py                 # Flask backend
├── requirements.txt       # Python bağımlılıkları
├── README.md             # Bu dosya
└── templates/
    ├── base.html         # Ana şablon (header, footer, tema)
    ├── index.html        # Ana sayfa (URL girişi)
    ├── loading.html      # Analiz yükleme ekranı
    └── results.html      # Analiz sonuçları
```

## 🎨 Özellikler

- **Dark Theme**: Neon yeşil aksanlı karanlık tema
- **Glassmorphism**: Modern cam efektli paneller
- **Responsive**: Mobil ve masaüstü uyumlu
- **Animasyonlar**: Yükleme spinner'ı, fade-in efektleri, progress bar'lar
- **Demo Mod**: URL hash'ine göre tutarlı mock veri üretimi

## 🔧 Geliştirme

### Gerçek API Entegrasyonu

`MockAnalyzer` sınıfını gerçek bir analiz servisi ile değiştirin:

```python
# app.py içinde MockAnalyzer yerine:
class RealAnalyzer:
    def __init__(self, url):
        self.url = url

    def analyze(self):
        # Burada gerçek web scraping veya API çağrısı yapın
        # BeautifulSoup, Selenium, veya harici bir AI API kullanabilirsiniz
        pass
```

### Ortam Değişkenleri

`.env` dosyası oluşturun:

```
FLASK_ENV=production
SECRET_KEY=your-secret-key-here
```

## 📝 Notlar

- Bu demo versiyonunda analizler URL hash'ine göre tutarlı mock veriler üretir
- Gerçek e-ticaret sitelerinden veri çekmek için web scraping veya API entegrasyonu gereklidir
- Trendyol, Amazon, Hepsiburada gibi sitelerin API'leri veya scraping kuralları değişebilir

## 📄 Lisans

MIT License