# refcheck: Referans Kontrol MCP Sunucusu

Yapay zekâ yardımıyla yazılan makalelerde **uydurma (halüsinasyon) veya hatalı
künyeli referansları** gönderimden önce yakalamak için bir MCP sunucusu.
Referansları Crossref ve OpenAlex'te arar; gerçek kaydı bulursa alan alan
karşılaştırır ve düzeltilmiş BibTeX'i verir.

## Araçlar

| Araç | Ne yapar |
|---|---|
| `check_references` | Bir referans listesinin tamamını kontrol eder (BibTeX veya APA/IEEE gibi düz metin) |
| `verify_reference` | Tek bir referansı kontrol eder |
| `search_literature` | Bir konu veya iddia için **gerçek** makaleleri, BibTeX'leriyle birlikte bulur |
| `get_bibtex` | Bir DOI için doğru BibTeX üretir |

### Sonuç durumları

| Durum | Anlamı |
|---|---|
| `verified` | Gerçek kayıt bulundu, bilgiler tutarlı (küçük notlar olabilir) |
| `needs_correction` | Eser var ama künyede hata var (yıl, yazar, DOI, geri çekilmiş...). Düzeltilmiş BibTeX verilir |
| `possible_match` | Benzer bir eser var ama emin olunamadı. Yazar kontrol etmeli |
| `not_found` | Hiçbir kaynakta yok, **muhtemelen uydurma**. Varsa yakın adaylar `did_you_mean` altında listelenir |
| `unverifiable` | Kitap, tez, rapor, web sayfası gibi indekslerde çoğu zaman bulunmayan bir kaynak. Elle kontrol edilmeli |
| `error` | Kaynaklara ulaşılamadı |

Yakalanan uydurma tipleri: tamamen uydurma eser, gerçek başlık ama uydurma yazarlar,
var olmayan DOI, başka bir makaleye ait DOI, yanlış yıl/cilt/sayfa, geri çekilmiş
(retracted) makale, gerçek başlığa eklenmiş uydurma alt başlık.

## Kurulum

```powershell
git clone <repo-url> refcheck
cd refcheck
python -m venv .venv
.\.venv\Scripts\pip install -e .
```

### Claude Desktop

`%APPDATA%\Claude\claude_desktop_config.json` dosyasına ekleyin (yolu kendi
kurulumunuza göre değiştirin):

```json
{
  "mcpServers": {
    "refcheck": {
      "command": "C:\\yol\\refcheck\\.venv\\Scripts\\refcheck-mcp.exe",
      "env": { "REFCHECK_MAILTO": "lab-iletisim@ornek.edu.tr" }
    }
  }
}
```

### Claude Code

```powershell
claude mcp add refcheck -e REFCHECK_MAILTO=lab-iletisim@ornek.edu.tr -- C:\yol\refcheck\.venv\Scripts\refcheck-mcp.exe
```

Ardından Claude'a örneğin şunu söyleyebilirsiniz: *"Şu referans listesini kontrol et: ..."*
ya da *"Bu paragraf için gerçek kaynak bul."*

## Ayarlar (ortam değişkenleri)

| Değişken | Açıklama |
|---|---|
| `REFCHECK_MAILTO` | Crossref/OpenAlex'e gönderilen iletişim e-postası. "Polite pool"a girer; daha hızlı ve güvenilir. **Önerilir.** |
| `REFCHECK_OPENALEX_API_KEY` | (İsteğe bağlı) OpenAlex API anahtarı, yoğun kullanım için |
| `REFCHECK_CACHE` | Önbellek dosyasının yolu (varsayılan `%LOCALAPPDATA%\refcheck\cache.sqlite3`); `off` yazılırsa kapanır |

Sorgular 30 gün önbellekte tutulur; aynı referansı tekrar kontrol etmek API'ye gitmez.

## Geliştirme

```powershell
.\.venv\Scripts\pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest              # çevrimdışı testler
.\.venv\Scripts\python -m pytest -m live      # gerçek API'lerle uçtan uca testler
```

Kod yapısı (`src/refcheck/`):

- `parsing.py`: BibTeX ve düz metin referans listelerini ayrıştırır
- `sources.py`: Crossref, OpenAlex ve doi.org istemcileri
- `verify.py`: Eşleştirme ve karar mantığı (`assess()` saf fonksiyon, kolay test edilir)
- `normalize.py`: Metin normalizasyonu (Türkçe karakterler, LaTeX) ve benzerlik ölçüleri
- `bibtex.py`: Doğrulanmış kayıttan BibTeX üretimi
- `server.py`: MCP araçları

## Sınırlamalar ve yol haritası

- Kitaplar, tezler ve Türkçe yerel dergiler indekslerde eksik olabilir (`unverifiable`).
  Sırada **DergiPark** ve **TR Dizin** desteği var.
- Alana göre ek kaynaklar eklenebilir: arXiv, DBLP, PubMed, Semantic Scholar.
- PDF ve Word taslaklarından referans listesini otomatik çıkarma (GROBID).
- Yazar–konu tutarlılığı (yazarlar gerçek mi, bu alanda yayınları var mı?).
- Atıfın, alıntılanan cümledeki iddiayı gerçekten destekleyip desteklemediği.
- Labın kullandığı atıf stillerinde (APA, IEEE...) format kontrolü.
