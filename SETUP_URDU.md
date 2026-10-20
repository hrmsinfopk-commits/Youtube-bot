# Bot Setup Guide (Roman Urdu)

Yeh sab kaam **ek hi dafa** karna hai. Laptop/computer par browser se karein (mobile par Google Cloud wala hissa mushkil hai). Kul waqt: 30–40 minute. Sab kuch **free** hai.

Aapko 6 "keys" jama karni hain, phir unhein GitHub mein daalna hai:

| Naam (bilkul aise hi likhna) | Kahan se milegi |
|---|---|
| `GEMINI_API_KEY` | Step 2 |
| `PEXELS_API_KEY` | Step 3 |
| `PIXABAY_API_KEY` | Step 3 |
| `YT_CLIENT_ID` | Step 4 |
| `YT_CLIENT_SECRET` | Step 4 |
| `YT_REFRESH_TOKEN` | Step 4 |

Ek Notepad khol lein aur har key wahan copy karte jayen.

---

## Step 1: GitHub par bot daalna

1. **github.com** par free account banayen (agar nahi hai).
2. Oopar right mein **+** → **New repository**.
   - Name: `yt-bot`
   - **Private** chunein
   - **Create repository**
3. Naye page par link **"uploading an existing file"** par click karein.
4. Zip file ko unzip karein. `yt-bot` folder ke **andar ki saari cheezein** (folders bhi) browser mein drag karke chhod dein → neeche **Commit changes**.
5. Check karein ke repo mein `.github/workflows/shorts.yml` aur `long.yml` nazar aa rahi hain.
   - Agar `.github` folder upload nahi hua (Mac par hidden hota hai): **Add file → Create new file**, naam mein likhein `.github/workflows/shorts.yml`, aur zip wali file ka saara text paste kar dein. Phir `long.yml` ke liye bhi yahi karein.
6. Repo mein **Settings → Actions → General** → neeche **Workflow permissions** → **Read and write permissions** → Save.

## Step 2: Gemini key (script likhne wala AI)

1. **aistudio.google.com/apikey** kholen, Google account se login karein.
2. **Create API key** → key copy karke Notepad mein `GEMINI_API_KEY` ke saamne rakh lein.

## Step 3: Footage keys (free videos/photos)

1. **pexels.com/api** → **Get Started** → account banayen → form bharen (website ki jagah apne YouTube channel ka link) → key copy → `PEXELS_API_KEY`.
2. **pixabay.com** par account banayen → phir **pixabay.com/api/docs** kholen → page par "key" ke saamne aapki key likhi hogi → copy → `PIXABAY_API_KEY`.

## Step 4: YouTube upload ki ijazat (sab se lamba step, 15 minute)

**A. Google Cloud project**
1. **console.cloud.google.com** kholen (wohi Google account jis par YouTube channel hai).
2. Oopar project list → **New Project** → naam `yt-bot` → Create.
3. Search bar mein **YouTube Data API v3** likhein → kholen → **Enable**.

**B. OAuth consent screen**
1. Left menu → **APIs & Services → OAuth consent screen** (naye design mein: **Google Auth Platform**) → **Get started**.
2. App name: `yt-bot`, apni email → **External** → apni email → Create.
3. **Audience** mein jayen → **Publish app** → Confirm, taake status **"In production"** ho jaye.
   > ⚠️ Yeh zaroor karein. Agar "Testing" mein raha to bot 7 din baad upload karna band kar dega.

**C. Client ID / Secret**
1. **Clients** (ya Credentials) → **Create client** → Application type: **Web application**.
2. **Authorized redirect URIs** → Add URI → bilkul yeh paste karein:
   `https://developers.google.com/oauthplayground`
3. Create → **Client ID** aur **Client secret** copy karke `YT_CLIENT_ID` aur `YT_CLIENT_SECRET` mein rakh lein.

**D. Refresh token**
1. **developers.google.com/oauthplayground** kholen.
2. Right side mein ⚙️ (gear) → ✅ **Use your own OAuth credentials** → apni Client ID aur Secret paste karein.
3. Left side mein "Input your own scopes" wale box mein yeh paste karein:
   `https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly`
4. **Authorize APIs** → apna YouTube wala Google account chunein → **apna channel** chunein.
5. "Google hasn't verified this app" aaye to **Advanced → Go to yt-bot (unsafe)** dabayen. Yeh aapki apni app hai, koi khatra nahi. Saare boxes tick karke **Continue**.
6. **Exchange authorization code for tokens** dabayen → **Refresh token** copy → `YT_REFRESH_TOKEN`.

## Step 5: Keys GitHub mein daalna

1. Apni repo → **Settings → Secrets and variables → Actions** → **New repository secret**.
2. Har key ke liye: **Name** mein upar wala naam (jaise `GEMINI_API_KEY`), **Secret** mein key → Add.
3. Chhe ki chhe keys daal dein. (Yeh secret rehti hain, kisi ko nazar nahi aati.)

## Step 6: Pehla test

1. Repo mein **Actions** tab → agar button aaye to **"I understand my workflows, enable them"**.
2. Left mein **Daily Shorts** → **Run workflow** → Run.
3. 8–15 minute baad:
   - ✅ Hara nishan = video YouTube par aa gayi. Studio check karein.
   - Run kholen → neeche **Artifacts** se video download bhi kar sakte hain.
   - ❌ Laal nishan = run kholen, laal step ka screenshot le kar mujhe bhej dein.
4. Phir **Long Videos** → Run workflow se long video test karein (25–45 minute lagte hain).

Is ke baad bot **khud** chalta rahega. Aapko kuch nahi karna.

---

## Zaroori extra kaam (ek dafa)

- **Phone verify:** youtube.com/verify. Is ke baghair custom thumbnail nahi lagta.
- **Music:** YouTube Studio → Audio Library se 5–10 "No attribution required" songs download karein → GitHub repo ke `music` folder mein **Add file → Upload files**.
- **Channel ko tayyar karein:** naam, logo, banner, aur About mein keywords ("AI, future technology, robots, science Urdu mein").

## Settings kaise badlein

GitHub par `config.yaml` kholen → ✏️ (pencil) → badlein → **Commit changes**.
- Topic badalna: `niche:`
- Hindi awaaz: `language: "hindi"`
- Videos pehle khud dekhna: `privacy: "private"`
- Apne topics: `topics.txt` mein har line par ek topic likhein. Bot pehle wahi banayega.
- Waqt badalna: `.github/workflows/shorts.yml` mein `cron` (UTC time; Pakistan = UTC + 5).

## Masle aur hal

| Masla | Hal |
|---|---|
| Video upload hui magar **private** hai | Google naye API projects ko kabhi kabhi private tak rokta hai. Studio se Public kar dein, aur Google ka "YouTube API Services audit" form bharen (free). |
| 7 din baad upload band | Step 4-B mein app "In production" nahi ki thi. Publish karein aur Step 4-D dobara karke naya token daalein. |
| "Koi footage nahi mili" | Pexels/Pixabay key check karein. |
| Gemini error 429 | Free limit poori ho gayi. Bot agle run mein khud theek ho jayega. |
| Minutes khatam (private repo: 2,000 min/mahina free) | Repo ko Public kar dein (Settings → Danger zone). Keys phir bhi secret rehti hain. |

## Imandari wali baatein

- Views ki guarantee koi bot nahi de sakta. Pehle 2–4 hafte views kam aana normal hai. Mustaqil rehna sab se zaroori hai.
- YouTube **mukammal automated, ek jaisi** videos wale channels ko monetization mein reject kar sakta hai. Bot har video alag banata hai, lekin hafte mein 10 minute nikal kar kuch videos dekh lein. Agar kabhi kabhi apni awaaz wali video bhi daal saken to monetization ke chances kaafi barh jate hain.
- YouTube Studio → Analytics mein dekhte rahen ke kaunse topics chal rahe hain, aur waise topics `topics.txt` mein daal dein.
