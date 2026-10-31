# University of Layyah — AI Chatbot (RAG)

Yeh chatbot **sirf university ki website ke content** se jawab deta hai (Urdu, Roman Urdu, English).

```
ul.edu.pk ──► crawler ──► chunking ──► embeddings ──► index (data/index)
                                                         │
 student ► widget (chatbot.js) ► FastAPI /api/chat ──────┤
                                   │  1. sawal ko English search-query mein badalna (history ke saath)
                                   │  2. Hybrid search: dense vectors + BM25 → RRF fusion
                                   │  3. Claude: sirf mile hue context se jawab + sources
                                   ▼
                            jawab + source links
```

## 1. Setup (ek baar)

Python 3.10+ chahiye.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # phir .env mein ANTHROPIC_API_KEY daalein
```

API key: https://console.anthropic.com se banayein.

## 2. Website ka data jama karein aur index banayein

```bash
python -m app.crawler     # ul.edu.pk ke pages + PDFs -> data/raw/pages.jsonl
python -m app.ingest      # chunks + embeddings -> data/index/
```

Pehli baar `ingest` embedding model download karta hai (~470 MB, ek dafa).

**Zaroori:** `data/raw/pages.jsonl` kholkar dekhein ke Fee Structure, Eligibility, Admission Schedule
wale pages ka text aa gaya hai. Agar koi page sirf **image** ya JavaScript se load hota hai to uska text
`data/manual/` mein ek `.md` file bana kar likh dein (misal: `data/manual/fee.md`). Dobara `python -m app.ingest` chalayein.

## 3. Chalayein

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Browser mein http://localhost:8000 kholein — neeche chat button aayega.
Health check: http://localhost:8000/api/health (`"status":"ok"` aur chunks ki ginti).

## 4. University website par lagana

Server deploy karne ke baad (neeche dekhein), website ke footer template mein sirf yeh line add karwayein:

```html
<script src="https://chatbot.aapka-domain.com/static/chatbot.js" defer></script>
```

Optional: `data-color="#0f4c5c"` (rang), `data-api="https://..."` (agar API alag jagah ho).
`.env` mein `ALLOWED_ORIGINS` mein website ka domain hona chahiye (default: ul.edu.pk).

> Footer edit karne ke liye university ke IT/webmaster ki ijazat aur access chahiye hoga.

## 5. Deploy

- **VPS / university server:** `uvicorn` ko `systemd` ya `supervisor` se chalayein, aage **nginx + HTTPS** (Let's Encrypt) lagayein.
  Nginx ke peeche ho to `.env` mein `TRUST_PROXY=true` karein (taake rate-limit asli IP par lage).
- **Docker:** `docker build -t ul-chatbot .` phir  
  `docker run -p 8000:8000 --env-file .env -v $(pwd)/data:/srv/data ul-chatbot`
- Widget HTTPS website par chal raha ho to API bhi HTTPS par honi chahiye.

## 6. Data update rakhna

Naye notices/admission dates ke liye hafte mein ek baar:

```bash
python -m app.crawler && python -m app.ingest && sudo systemctl restart ul-chatbot
```
(cron mein laga dein.)

## 7. Tests

```bash
python -m unittest discover -s tests -v
```
Yeh offline hain (network ya API key nahi chahiye).

## Customize

| Cheez | Kahan |
|---|---|
| Chatbot ka mizaaj / rules | `SYSTEM_PROMPT` in `app/llm.py` |
| Claude model | `.env` → `CLAUDE_MODEL` |
| Chunk size, top-k | `.env` → `CHUNK_WORDS`, `TOP_K` |
| Widget ke rang, greeting, quick buttons | `static/chatbot.js` (upar `GREETING`, `QUICK`) |
| Crawler ke seed pages | `SEED_PATHS` in `app/crawler.py` |
| Extra facts (fee, FAQ) | `data/manual/*.md` |

## Mehfooz rakhne ke liye

- Student ka personal data (CNIC, result, UMS login) chatbot ko **mat dein**. Bot sirf public info ke liye hai.
- API key kabhi widget/JS mein mat daalein — woh sirf server ki `.env` mein rehti hai.
- Rate limit (`RATE_LIMIT_PER_MIN`) aur CORS pehle se on hain. Claude API ka kharcha bhi console mein limit kar dein.
- Crawler `robots.txt` ka ehtram karta hai aur har request ke beech wakfa deta hai.

## Masle aur hal

| Masla | Hal |
|---|---|
| `status: index_missing` | Crawler aur ingest chalayein, server restart karein |
| Jawab "nahi mila" aata hai | `pages.jsonl` mein us page ka text dekhein; zarurat ho to `data/manual/` mein likhein |
| Widget nahi dikhta / CORS error | `ALLOWED_ORIGINS` mein website ka domain daalein |
| 502 error | `ANTHROPIC_API_KEY`, model naam aur credit check karein (server log dekhein) |
