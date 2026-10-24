# 🤖 Tomorrowly Bot – Chalane ki Guide (Roman Urdu)

Yeh bot GitHub par **khud** chalta hai. Aap ka computer band ho tab bhi. Is guide mein woh sab hai jo aap ko rozmarra mein chahiye.

---

## 1. Bot kya karta hai (khud-ba-khud)

| Kya | Kab (Pakistan time) |
|---|---|
| **Short** (30–50 sec, vertical) | Roz shaam 7 baje |
| **Long video** (3–4 min, ek topic ki poori kahani) | Wednesday aur Saturday shaam 6 baje |
| **Analytics** (views, retention, engagement) | Roz subah 8 baje |
| **Haftawar report** (`REPORT.md`) | Har Monday subah |

Har video mein bot khud:
1. Taaza khabrein (Google News, NASA, Hacker News) **aur** YouTube par is hafte kya chal raha hai, dekh kar topic chunta hai
2. `writer_brief.md` ke mutabiq apni original script likhta hai (aur pichli scripts se milata hai taake kuch dohraya na jaye)
3. Mustaqil narrator ki awaaz (Gemini "Charon")
4. Har line ke liye fitting footage chunta hai (NASA, Pixabay, Wikimedia, Openverse) – credit ke saath
5. Apne graphics banata hai: **Hype Meter, Tomorrow Test**, numbers, bars, timeline
6. Captions (awaaz ke saath sync), music, sound effects, logo
7. SEO title, description, tags ke saath YouTube par upload

---

## 2. Aap ke kaam (sab GitHub website ya mobile app se)

### Apna topic dena – `topics.txt`
File kholen → ✏️ → line likhen → **Commit changes**.

```
Tesla's new robotaxi – is it really driverless?
long: Everything about NASA's next Moon mission
SpaceX Starship test | my take: I think they'll succeed by next year
```
- Aam line = **Short** ke liye
- `long:` se shuru = **long video** ke liye
- ` | ` ke baad **apni raye** – script mein shamil ho jayegi
- List khali ho to bot khud trending topic dhoondta hai. Use hone wali line bot khud hata deta hai.

### Script writer ki hidayat – `writer_brief.md`
Yeh aap ke "employee" ka brief hai: narrator ki shakhsiyat, kya kabhi nahi kehna, aur channel ke signature hisse
(The Catch, We Did The Math, Hype Meter, Tomorrow Test). Badalna ho to yahin badlen.

### Aam settings – `config.yaml`

| Setting | Kya karti hai |
|---|---|
| `privacy: "public"` | `private` karein to videos pehle sirf aap ko nazar aayengi |
| `long_privacy: "private"` | Long videos alag se private/public. **Long video pasand aaye to isay `"public"` kar dein** |
| `shorts: target_seconds: 40` | Short ki lambai |
| `long: target_minutes: 3.5` | Long video ki lambai |
| `host_voice: "Charon"` | Narrator ki awaaz (Gemini ki awaazein: Charon, Orus, Puck, Kore, Aoede...) |
| `brand_color` | Captions/graphics ka rang |

### Abhi foran video banwana
**Actions** → left mein workflow chunein (**Tomorrowly Shorts** / **Tomorrowly Long Videos**) → **Run workflow**.

**Test (upload ke baghair):** `.github/trigger-short.txt` (ya `trigger-long.txt`) kholen → ✏️ → `test` likhen → Commit.
Video ban kar Actions ke run mein **Artifacts** se download ho sakti hai, upload nahi hogi.

### Report dekhna
- `REPORT.md` – har Monday: subscribers/watch hours ka target, sab se achhi/kamzor videos aur wajah, bot ne kya seekha
- `data/last_run_future_short.log` / `..._long.log` – aakhri run mein kya hua

---

## 3. Masle aur hal

| Masla | Hal |
|---|---|
| GitHub se email: run **failed** | Actions → laal ❌ run → laal step ka screenshot le kar kisi bhi AI/developer ko dikhayen |
| Log mein `Gemini ... 404` | Google ne model band kar diya. `config.yaml` → `gemini: models:` mein naya model naam (aistudio.google.com par dekhein) |
| Log mein `429 quota` | Free limit poori. Khud theek ho jata hai (roz dopahar ~12-1 baje reset) |
| Log mein `invalid_grant` | YouTube token bekaar (password badla ya ijazat hatayi). OAuth Playground se naya refresh token banayen → GitHub Secrets → `YT_REFRESH_TOKEN` update |
| Video private aa rahi hai | `config.yaml` mein `privacy` / `long_privacy` check karein |
| Koi video pasand nahi | YouTube Studio se private/delete. `writer_brief.md` mein hidayat badal dein |

**GitHub Secrets** (Settings → Secrets and variables → Actions):
`GEMINI_API_KEY`, `PIXABAY_API_KEY`, `FREESOUND_API_KEY`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`
(optional: `PEXELS_API_KEY`, `POLLINATIONS_TOKEN`)

---

## 4. Madad chahiye?

Kisi bhi nayi Claude chat mein GitHub connect karein aur kahen:
*"Meri repo hrmsinfopk-commits/Youtube-bot mein YouTube bot hai, BOT_GUIDE.md parho aur yeh masla theek karo: ..."*
Saara code aur settings repo mein hain, is liye koi bhi wahin se kaam aage badha sakta hai.

⚠️ **Kabhi bhi apni keys/token chat mein paste na karein** – sirf GitHub Secrets mein.

## 📰 Khabar aur ❓ Bara sawal (do qisam ki videos)

- **Long videos:** Budh = trending khabar, Hafta = "bara sawal" (sada-bahar explainer, jaise "How a Country With Zero Rivers Drinks Water").
- **Shorts:** Somvaar aur Jumeraat = "bara sawal", baqi din trending khabar.
- Din badalne hon to `config.yaml` mein `long.formats_by_day` aur `shorts.big_question_days` badlein.
- Titles hamesha ek ulti/hairaan karne wali baat + How/Why par bante hain; thumbnail ke liye writer woh scene chunta hai jo ek nazar mein kahani bata de.
- Haftawar `REPORT.md` mein "Khabar vs Bara sawal" ka hisaab aata hai - 4 hafte baad jo behtar chale us ke din barha denge.

## 🔎 Har Somvaar: viral Shorts ka mutala
- Bot hamare niche ki pichhle 30 din ki sab se viral ~12 Shorts dhoondta hai, Gemini unhein khud "dekhta" hai (download nahi hota),
  aur un ke patterns se script writer ki playbook (`data/playbook_future.json`) update hoti hai.
- Kisi khaas video se seekhwana ho to uska link `inspiration.txt` mein daal dein.
- Monday ki `REPORT.md` mein "Viral Shorts ka mutala" section mein khulasa aata hai.

## 🛡️ Monetization protocol (quality gate)
Har video upload se pehle bot yeh check karta hai (aur jo ho sake khud theek karta hai):
1. Apni graphics: Short mein 1+, long mein 4+ (kam hon to graphics editor khud daalta hai).
2. Long video ki ~22%+ narration hamari apni graphics par (sirf "AI awaaz + stock footage" nahi).
3. Fact check: har daawa fact sheet se milaya jata hai; ghalat/be-saboot line badal di jati hai.
4. Khabar ke alfaaz copy nahi (overlap check).
5. Tasveer = alfaaz: kam az kam 80% scenes par fitting footage/graphics; AI tasveerein 20% se zyada nahi.
6. AI tasveer ho to YouTube ka "altered/synthetic content" label khud lagta hai.
7. Koi hard rule fail ho to video upload NAHI hoti (sirf GitHub artifact).
Monday ki REPORT.md mein har video ka gate result aata hai.
