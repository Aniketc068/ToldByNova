# Told By Nova - YouTube Shorts Automation Bot

**100% Free & Open Source** | [MIT License](LICENSE)

A fully automated YouTube Shorts factory controlled entirely from Telegram. AI generates viral stories, human-quality voice narrates them, FFmpeg builds pro-quality videos with effects, and YouTube uploads are scheduled at peak USA viewing hours - all hands-free.

**1,060+ subscribers and 18,500+ views in 6 days** - every video automated from story to upload.

### Top Performing Videos (Bot-Generated)

| # | Video | Views |
|---|-------|-------|
| 1 | [Karen's Midnight Raid Backfires](https://youtube.com/shorts/ikziz7pWbac) | 1,472 |
| 2 | [He Sued Red Bull Because It Didn't Give Him Wings](https://youtube.com/shorts/DzBWc4Ve3X4) | 1,326 |
| 3 | [She Found His Secret Phone and Destroyed His Life](https://youtube.com/shorts/okfESIzlBZU) | 1,237 |

---

## Live Proof - Channel Analytics (Started May 12, 2026)

| Metric | Value |
|--------|-------|
| Channel | [Told By Nova](https://www.youtube.com/@ToldByNova) |
| Started | May 12, 2026 |
| Subscribers | 1,060+ (in 6 days) |
| Total Views | 18,500+ |
| Total Videos | 22 |
| Avg Views/Short | 900-1,300 per video |
| Upload Frequency | 4 videos/day (fully automated scheduling) |
| Best Performing | "He Sued Red Bull Because It Didn't Give Him Wings" - 1,326 views |

### Video Performance (All Bot-Generated)

| Date | Video | Views | Likes | Duration |
|------|-------|-------|-------|----------|
| May 17 | Landlord Steals Deposit Then Loses Everything | 1,242 | 22 | 34s |
| May 17 | Banned Athlete Sues For Millions | 1,078 | 15 | 36s |
| May 17 | Entitled Neighbor Messes With Dogs | 1,013 | 16 | 35s |
| May 16 | He Thought He Was Dining In Peace | 1,204 | 10 | 32s |
| May 16 | He Picked The Worst Song Ever | 912 | 4 | 36s |
| May 16 | Karen's Midnight Raid Backfires | 1,472 | 30 | 36s |
| May 15 | Delivery Driver Steals Pet Cat on Camera | 1,140 | 11 | 36s |
| May 15 | He Asked Me To Help Him Cheat | 1,073 | 7 | 32s |
| May 15 | She Found His Secret Phone and Destroyed His Life | 1,237 | 12 | 34s |
| May 14 | She Found Every Receipt and Made Him Pay in Court | 970 | 16 | 37s |
| May 14 | He Said 'Do You Know Who I Am' to the Wrong Person | 965 | 19 | 35s |
| May 13 | She Tested Subway's Tuna and Called a Lawyer | 1,087 | 17 | 43s |
| May 13 | She Almost Threw Away a $24 Million Lottery Ticket | 1,107 | 55 | 41s |
| May 13 | Walmart Cashier Saw a Girl Mouth 'HELP ME' | 879 | 15 | 45s |
| May 13 | He Sued Red Bull Because It Didn't Give Him Wings | 1,326 | 28 | 33s |
| May 12 | Everyone Laughed When She Sued McDonald's Over Coffee | 954 | 48 | 43s |
| May 13 | She Called 911 and Ordered a Pizza to Escape Him | 1,085 | 8 | 34s |

**Key Finding:** 33-38 second videos consistently get 900-1,300+ views. Videos over 45 seconds perform worse. The bot targets 33-38s by default.

---

## What This Bot Does (Complete Feature List)

### Content Creation (AI-Powered)
- AI story generation with viral hook-first structure (revenge, karma, drama, justice, court stories)
- Real-time web search (DuckDuckGo) for trending Reddit/viral story leads
- Story structure enforced: Hook -> Escalation -> Second Hook (15s retention gate) -> Twist -> CTA -> Loop Cliffhanger
- Seamless loop trick - last line is an open-ended cliffhanger so YouTube Shorts auto-loop makes viewers think the story continues
- Duplicate detection - title similarity (60% overlap), script MD5 hash, exact match
- Manual story submission with AI refinement
- Duration targeting: 33-38s sweet spot (configurable 15-180s)

### Voice (Human-Quality)
- ElevenLabs TTS with multi-account key rotation (waterfall - tries each key until one works)
- Mood-based automatic voice selection - 5 different female voices matched to story mood
- Edge TTS fallback (Microsoft Emma Neural) - always available, free, unlimited
- Word-level SRT subtitle generation from both engines
- Per-key quota monitoring with live status check

### Voice Mood Mapping
| Mood | Voice | Style |
|------|-------|-------|
| Suspense / Dark / Horror | Lily | Velvety, dramatic |
| Dramatic / Revenge / Justice | Sarah | Mature, confident (default) |
| Happy / Upbeat / Funny | Jessica | Playful, bright |
| Emotional / Sad / Heartfelt | Elise | Warm, natural |
| Mysterious / Twist | Laura | Enthusiastic, quirky |

### Video Pipeline (FFmpeg)
- Multi-threaded segment building (3-4 parallel workers)
- GPU encoding (NVENC) with automatic CPU fallback
- 6 random subtitle color styles with dramatic word highlighting (68 keywords like "fired", "pregnant", "million", "arrested" shown in highlight color)
- Mood-based background music (5 moods) with 15-second delayed fade-in
- Subscribe overlay (chromakey green screen removal) timed to narrator
- Vignette effect for cinematic look
- Auto video compression for Telegram preview (720p -> 480p fallback)

### YouTube Upload & SEO
- Resumable chunked upload (10MB chunks) with 10 retry attempts
- Scheduled publishing - uploaded as private, auto-publishes at slot time
- 4 daily upload slots optimized for USA peak hours
- AI-generated SEO: title (<50 chars, curiosity gap), description (hook + summary + CTA + 3 hashtags), 20 tags (<480 chars)
- Title/tag/description sanitization (no emojis in title, no # in tags, hashtag limit in desc)
- Location metadata set to New York, USA for algorithm targeting

### Post-Upload Automation (All Automatic)
- Multilingual captions - English + Spanish, French, German, Portuguese (AI-translated)
- Auto-playlist management - creates and maintains playlist
- Pinned comment - AI-generated engaging question, deferred until video goes public
- Auto-reply to viewer comments - replies to first 5 comments with rotating templates (runs 60 min after publish)
- A/B title testing - generates 2 alternative titles, checks views after 48h, auto-swaps if underperforming (<50 views)
- AI thumbnail generation - 6 model chain (Pollinations.ai) + Pillow fallback with mood-based styling
- Custom thumbnail upload via YouTube API
- Community post text generation

### Multi-System Instance Lock + Data Sync
- Run the bot on multiple systems (HOME, OFFICE, LAPTOP, etc.) without conflicts
- Google Doc acts as a live ON/OFF switch - write `HOME=ON` / `OFFICE=OFF` to control which system runs
- Bot reads the doc every 5 seconds - if turned OFF, shuts down instantly with Telegram notification
- Google Drive data sync - all `data/` config files sync to Drive every 10 seconds
- On startup, bot downloads latest data from Drive so the new system continues where the last one left off
- One-time OAuth setup per system via `/auth_drive` command
- Add unlimited systems - just add `system_NAME=ip1,ip2` in `.env`

### Bot Management
- Multi-user access control (admin + invited users)
- Live slot countdown reminders (updated every 30s, color-coded progress bar)
- Pipeline resume after crash or restart
- Graceful stop system for long operations
- Persistent background job queue (survives restarts)
- Auto-restart service wrapper (50 restart limit with log rotation)
- Duplicate bot instance detection (409 Conflict handling)

---

## Architecture

```
Telegram Bot (telegram_automation.py - 4700+ lines)
    |
    +-- AI Story Generation (waterfall)
    |     +-- Primary: TrexoCLI / Claude Code / Codex (auto-detected)
    |     +-- Fallback: Ollama Cloud API (Gemma 4)
    |     +-- Web Search: DuckDuckGo (trending stories + SEO keywords)
    |
    +-- Voice Generation (voice_generator.py)
    |     +-- Primary: ElevenLabs (multi-key waterfall, mood-based voice)
    |     +-- Fallback: Edge TTS (Microsoft Emma Neural)
    |     +-- Output: MP3 + word-level SRT
    |
    +-- Video Pipeline (pipeline.py)
    |     +-- Clip sequencing (user clips + default clips, shuffled)
    |     +-- ASS subtitles (word-by-word, 6 random color styles)
    |     +-- BGM mixing (mood-based, 15s delayed fade-in)
    |     +-- Subscribe overlay (chromakey green screen)
    |     +-- Effects: vignette, color enhance, unsharp mask
    |     +-- GPU (NVENC) with CPU (libx264) fallback
    |
    +-- YouTube Upload (YouTube Data API v3)
    |     +-- Scheduled publishing (private -> public at slot time)
    |     +-- SEO metadata (AI-generated title, desc, tags)
    |     +-- Resumable chunked upload with retry
    |
    +-- Post-Upload PRO Features (all automatic)
    |     +-- Multilingual captions (5 languages)
    |     +-- Playlist management
    |     +-- Pinned comment (deferred until public)
    |     +-- Auto-reply comments (60 min window)
    |     +-- A/B title testing (48h check)
    |     +-- AI thumbnail + upload
    |
    +-- Multi-System Lock + Sync
          +-- Google Doc ON/OFF switch (5s polling)
          +-- Google Drive data sync (10s interval)
          +-- Auto-download on startup, auto-upload on change
          +-- Instant shutdown when turned OFF via doc
```

---

## Complete Setup Guide (0 to 100%)

Follow every step in order. By the end, you will have a fully working bot that generates stories, builds videos, and uploads them to YouTube on a schedule - all controlled from Telegram.

---

### Step 1: Prerequisites

Install these before anything else:

| Tool | Version | How to Install |
|------|---------|----------------|
| **Python** | 3.12+ | [python.org/downloads](https://www.python.org/downloads/) - check "Add to PATH" during install |
| **FFmpeg** | 6.0+ | See below |
| **Git** | Any | [git-scm.com](https://git-scm.com/downloads) |

#### FFmpeg Installation

**Windows:**
1. Download from [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) - get the "essentials" build (ZIP)
2. Extract the ZIP to `C:\ffmpeg`
3. Add `C:\ffmpeg\bin` to your system PATH:
   - Press `Win + R` -> type `sysdm.cpl` -> press Enter
   - Go to **Advanced** tab -> **Environment Variables**
   - Under "System variables", find `Path` -> click **Edit**
   - Click **New** -> paste `C:\ffmpeg\bin`
   - Click OK on all dialogs
4. Verify: open a new terminal and run `ffmpeg -version`

**Mac:** `brew install ffmpeg`

**Linux:** `sudo apt update && sudo apt install ffmpeg`

---

### Step 2: Clone and Install

```bash
git clone https://github.com/Aniketc068/ToldByNova.git
cd ToldByNova
pip install -r requirements.txt
```

Dependencies installed: `edge-tts`, `google-auth`, `google-auth-oauthlib`, `google-api-python-client`, `httpx`, `Pillow`, `opencv-python-headless`, `rembg[cpu]`, `numpy`, `ddgs`

---

### Step 3: Create a Telegram Bot

1. Open Telegram, search for [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Choose a name (e.g., "Told By Nova") and username (e.g., `ToldByNovaBot`)
4. BotFather gives you a **Bot Token** - save it (looks like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

**Get your Telegram User ID:**
1. Search for [@userinfobot](https://t.me/userinfobot) on Telegram
2. Send `/start` - it replies with your **User ID** (a number like `123456789`)

---

### Step 4: Get an Ollama Cloud API Key

1. Go to [ollama.com](https://ollama.com) and create an account
2. Generate an API key from your dashboard
3. Save the key

> **Note:** The bot auto-detects CLI AI tools in this order: **TrexoCLI** -> **Claude Code** -> **Codex**. First one found is used as primary AI. If none installed, Ollama Cloud is used. The bot works perfectly with Ollama alone - CLI tools are optional.

---

### Step 5: Set Up Environment Variables

The bot reads all credentials from environment variables. No secrets in code.

#### Option A: Batch File (Windows - Recommended)

1. Copy `run_bot.example.bat` to `run_bot.bat`
2. Edit and fill in your credentials:

```bat
@echo off
cd /d "%~dp0"
set BOT_TOKEN=your_telegram_bot_token
set ADMIN_ID=your_telegram_user_id
set OLLAMA_API_KEY=your_ollama_api_key
set OLLAMA_MODEL=gemma4:31b-cloud
python scripts\telegram_automation.py
```

3. Save. `run_bot.bat` is gitignored - your secrets stay local.

#### Option B: Manual (Any OS)

**Windows PowerShell:**
```powershell
$env:BOT_TOKEN = "your_telegram_bot_token"
$env:ADMIN_ID = "your_telegram_user_id"
$env:OLLAMA_API_KEY = "your_ollama_api_key"
python scripts/telegram_automation.py
```

**Linux/Mac:**
```bash
export BOT_TOKEN="your_telegram_bot_token"
export ADMIN_ID="your_telegram_user_id"
export OLLAMA_API_KEY="your_ollama_api_key"
python scripts/telegram_automation.py
```

#### Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | Yes | Telegram bot token from @BotFather |
| `ADMIN_ID` | Yes | Your Telegram user ID (admin access) |
| `OLLAMA_API_KEY` | Yes | Ollama Cloud API key |
| `OLLAMA_MODEL` | No | AI model (default: `gemma4:31b-cloud`) |
| `OLLAMA_API` | No | API endpoint (default: `https://api.ollama.com/api/chat`) |
| `NOVA_PROJECT` | No | Project root path (auto-detected if not set) |

#### Bot Config File (`assets/channel/.env`)

Separate from environment variables, the bot also reads `assets/channel/.env` for project-level config:

| Key | Required | Description |
|-----|----------|-------------|
| `lock_doc` | No | Google Doc URL for multi-system ON/OFF switch |
| `lock_check_interval` | No | How often to check the doc (default: 5 seconds) |
| `system_NAME` | No | System IPs — `system_HOME=192.168.1.64,192.168.1.72` |
| `github` | No | GitHub personal access token (for private repo backup) |
| `public_repo` | No | Public GitHub repo URL |
| `private_repo` | No | Private GitHub repo URL |

See `assets/channel/.env.example` for a full template.

---

### Step 6: Get Video Clips (Copyright-Free)

The bot needs short video clips as visual backgrounds for narration.

| Type | Path | Description |
|------|------|-------------|
| **Default clips** | `assets/clips_default/` | Pre-loaded clips used when no custom clips provided |
| **Manual clips** | `assets/clips_manual/` | Clips sent via Telegram during video creation (per-video) |

#### Where to Download

All clips **must be 100% copyright-free**. Never take clips from YouTube - it will cause copyright strikes.

**Free Stock Video Sites:**

| Source | URL | License |
|--------|-----|---------|
| **Pexels** | [pexels.com/videos](https://www.pexels.com/videos/) | Free, no attribution |
| **Pixabay** | [pixabay.com/videos](https://pixabay.com/videos/) | Pixabay License (free) |
| **Coverr** | [coverr.co](https://coverr.co/) | Free to use |

#### Reference Apps for Satisfying Video Clips

These apps have massive libraries of satisfying/ASMR/oddly satisfying clips. Download clips from these platforms and use them as backgrounds for your narration videos.

| App | Platform | Why Use It | Notes |
|-----|----------|-----------|-------|
| **RedNote (Xiaohongshu)** | iOS / Android | #1 source for satisfying clips - soap cutting, slime, sand, calligraphy, cleaning. Huge library, high quality, vertical format ready. Most creators allow reuse. | Best source overall. Search: "satisfying", "ASMR", "oddly satisfying" |
| **TikTok** | iOS / Android | Massive satisfying video library. Use VPN if TikTok is banned in your country. | Download via save button or third-party tools. Bot auto-trims last 6s to remove watermarks |
| **Kuaishou** | iOS / Android | Chinese short video app with tons of satisfying/craft/cooking content. Less known but excellent quality clips. | Search in Chinese for best results: "解压" (decompression/satisfying) |

**Important:** The bot has built-in auto-trim that removes the last 6 seconds from clips (to cut watermarks from RedNote/TikTok). Enable with `/trim_on` (enabled by default).

**What to search for:** "satisfying" videos - soap cutting, slime mixing, calligraphy, cooking, nature close-ups, cleaning, organizing, restocking, pottery, sand kinetic. These work best as story narration backgrounds.

**Requirements:** MP4/WebM/MOV, at least 5 seconds, any resolution (auto-scaled to 1080x1920). Place 5-10 clips in `assets/clips_default/`.

---

### Step 7: Get Background Music (Copyright-Free)

5 mood-based BGM files required in `assets/bgm/`:

| Filename | Search For | Used When |
|----------|------------|-----------|
| `dramatic.mp3` | "dramatic cinematic background" | Default mood, intense stories |
| `suspense.mp3` | "suspense thriller background" | Mystery, crime stories |
| `emotional.mp3` | "emotional piano background" | Sad, touching stories |
| `uplifting.mp3` | "uplifting inspiring background" | Happy endings, feel-good |
| `dark.mp3` | "dark ambient background" | Horror, creepy stories |

**Sources:** [Pixabay Music](https://pixabay.com/music/), [OpenGameArt](https://opengameart.org/) (CC0), [Mixkit](https://mixkit.co/free-stock-music/)

Tips: instrumental only, 1-3 min (auto-looped), lower-energy tracks.

---

### Step 8: Subscribe Overlay (Optional)

1. Get a "subscribe button green screen" video from Pixabay or Pexels
2. Save as `assets/subscribe.mp4`
3. Must have solid green background (the bot uses chromakey to remove it)

If skipped, videos are built without subscribe overlay.

---

### Step 9: Set Up YouTube Upload (OAuth2)

Required only for auto-upload to YouTube. Skip if you prefer manual upload.

#### 9a: Create Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create new project (name it anything)

#### 9b: Enable APIs
Enable both:
- [YouTube Data API v3](https://console.cloud.google.com/apis/library/youtube.googleapis.com)
- [YouTube Analytics API](https://console.cloud.google.com/apis/library/youtubeanalytics.googleapis.com)

#### 9c: OAuth Consent Screen
1. Go to [OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent)
2. Select **External** -> Create
3. Fill app name, support email, developer email
4. Under **Test users**, add your Google account email

#### 9d: Create Credentials
1. Go to [Credentials](https://console.cloud.google.com/apis/credentials)
2. Create Credentials -> OAuth client ID -> Desktop app
3. Download JSON -> rename to `credentials.json` -> move to project root

#### 9e: First-Time Authorization

```bash
python -c "
from google_auth_oauthlib.flow import InstalledAppFlow
SCOPES = [
    'https://www.googleapis.com/auth/youtube',
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.force-ssl',
]
flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
creds = flow.run_local_server(port=8080)
with open('token.json', 'w') as f:
    f.write(creds.to_json())
print('Done! token.json created.')
"
```

Browser opens -> sign in with YouTube channel's Google account -> Allow all permissions. `token.json` created - auto-refreshes, you only do this once.

#### 9f: Verify

```bash
python -c "
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
with open('token.json') as f: td = json.load(f)
creds = Credentials(token=td['token'], refresh_token=td['refresh_token'],
    token_uri='https://oauth2.googleapis.com/token',
    client_id=td['client_id'], client_secret=td['client_secret'])
yt = build('youtube', 'v3', credentials=creds)
ch = yt.channels().list(part='snippet', mine=True).execute()
print(f'Connected to: {ch[\"items\"][0][\"snippet\"][\"title\"]}')
"
```

---

### Step 10: Set Up ElevenLabs Voice (Optional but Recommended)

ElevenLabs gives human-quality voice instead of robotic Edge TTS. Free tier = 10,000 characters/month per account. With 4 videos/day (~750 chars each), you need about 90,000-100,000 chars/month.

**Minimum accounts needed: 10** (10 x 10,000 = 100,000 chars/month = ~130 videos)

#### How to Set Up

1. Create 10+ ElevenLabs accounts at [elevenlabs.io](https://elevenlabs.io)
   - Use Gmail aliases: `you+el1@gmail.com`, `you+el2@gmail.com`, etc.
2. For each account: Profile (bottom-left) -> API Keys -> Create -> Copy key
3. Start the bot and add keys via Telegram:

```
/add_voice_key sk_abc123...
/add_voice_key sk_def456...
(repeat for all keys)
```

The bot validates each key automatically and activates ElevenLabs as the voice engine. Keys rotate automatically - when one runs out of quota, the next one is used. If all keys are exhausted, Edge TTS kicks in as fallback.

#### Voice Management Commands

| Command | What It Does |
|---------|-------------|
| `/add_voice_key <key>` | Add an ElevenLabs API key (auto-validates) |
| `/voice_keys` | List all saved keys |
| `/remove_voice_key <N>` | Remove key by index number |
| `/voice_api_status` | Live check - hits each key, shows chars used/remaining, renew date |
| `/voice elevenlabs` | Switch to ElevenLabs voice |
| `/voice edge` | Switch to Edge TTS voice |
| `/voice_id <id>` | Change ElevenLabs voice ID |

The bot automatically selects different voices based on story mood - no manual voice switching needed.

---

### Step 11: Multi-System Instance Lock + Data Sync (Optional)

Run the bot on multiple systems (home PC, office PC, laptop) without conflicts. A shared Google Doc acts as a live switch - only one system runs at a time, and data syncs automatically via Google Drive.

#### 11a: Configure Systems in `.env`

Edit `assets/channel/.env` (copy from `.env.example`):

```env
# Google Doc ON/OFF switch
# Create a Google Doc, share with "Anyone with the link can view"
lock_doc=https://docs.google.com/document/d/YOUR_DOC_ID/edit
lock_check_interval=5

# Add your systems - find IPs with: ipconfig (Windows) or ip addr (Linux)
system_HOME=192.168.1.64,192.168.1.72
system_OFFICE=10.0.0.50,10.0.0.51
# system_LAPTOP=192.168.0.200
```

- `lock_doc` — URL of your shared Google Doc
- `lock_check_interval` — how often to check the doc (seconds, default 5)
- `system_NAME=ip1,ip2` — each system's name and its local IP addresses (LAN + WiFi)

You can add as many systems as you want. The bot detects which system it's running on by matching local IPs.

#### 11b: Set Up the Google Doc

Create a Google Doc and share it with **"Anyone with the link can view"**. Write one line per system:

```
HOME=ON
OFFICE=OFF
```

To switch systems: change `HOME=OFF` and `OFFICE=ON` in the doc. The running bot detects the change within 5 seconds, sends a Telegram message "Shutting down from HOME", and exits. Then start the bot on the other system.

#### 11c: Enable Google Drive API

1. Go to [Google Cloud Console API Library](https://console.cloud.google.com/apis/library)
2. Select the same project used for YouTube API
3. Search **"Google Drive API"** → Click **Enable**
4. That's it — the same OAuth credentials (`yt_client_secret_1.json`) work for Drive too

#### 11d: Authorize Google Drive (One-Time Per System)

1. Start the bot on the system
2. Send `/auth_drive` in Telegram
3. Bot sends an OAuth URL → open in browser → authorize → copy the code
4. Paste the code in Telegram chat
5. Bot saves the Drive token — sync is now active

After authorization, the bot:
- **On startup**: downloads all data files from Google Drive (gets latest state from whichever system ran last)
- **Every 10 seconds**: checks for changed files and uploads only what changed
- **On shutdown**: does a final forced sync to Drive

#### 11e: Switching Between Systems

```
1. Change Google Doc: HOME=OFF, OFFICE=ON
2. HOME bot detects OFF → syncs data to Drive → shuts down
3. Start bot on OFFICE → downloads data from Drive → continues where HOME left off
4. All story history, upload schedule, pending jobs carry over seamlessly
```

### Step 12: Run the Bot

**Option A: Batch file (Windows)**
```bash
run_bot.bat
```

**Option B: Service wrapper (auto-restarts on crash)**
```bash
python scripts/bot_service.py
```

**Option C: Manual**
```bash
python scripts/telegram_automation.py
```

The bot sends you a startup message on Telegram with status info. If instance lock is configured, the message shows `Lock: HOME | Sync: ON`.

---

### Step 13: Auto-Start on System Boot (Windows Task Scheduler)

So the bot starts automatically when your PC turns on:

1. Open Task Scheduler (`Win + R` -> `taskschd.msc`)
2. Click **Create Task** (not "Basic Task")
3. **General tab:**
   - Name: `ToldByNova_Bot`
   - Check "Run whether user is logged on or not"
   - Check "Run with highest privileges"
4. **Triggers tab:**
   - New -> Begin the task: "At startup"
   - Delay task for: 30 seconds
5. **Actions tab:**
   - New -> Action: Start a program
   - Program: `powershell.exe`
   - Arguments: `-ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\path\to\ToldByNova\start_bot.ps1"`
   - Start in: `C:\path\to\ToldByNova`
6. **Settings tab:**
   - Check "Allow task to be run on demand"
   - Check "If the task fails, restart every 1 minute" (up to 3 times)
7. Click OK

The bot now starts automatically on every system boot. The service wrapper (`bot_service.py`) handles crash recovery with auto-restart (up to 50 restarts with daily log rotation).

---

## How to Use the Bot (Full Workflow)

Everything is controlled from Telegram. No terminal needed after setup.

### Creating a Video (Start to Finish)

```
/auto                    -> Bot generates AI story
/1                       -> Pick the story (or /more for new options)
/ok                      -> Approve story -> voice + subtitles generated
(optional) /clips        -> Send custom video clips
(optional) /done         -> Finish collecting clips
/build                   -> Bot builds video with effects, BGM, subtitles
(preview in Telegram)    -> Watch the preview
/ok                      -> Approve for upload
/upload                  -> Uploads to YouTube (scheduled at next slot)
/confirm                 -> Cleanup after upload
```

Or use your own story: `/story <paste your script>` -> `/ok` -> continue from `/build`

### All Commands

#### Content Creation
| Command | What It Does |
|---------|-------------|
| `/auto` | Generate AI story |
| `/story <text>` | Submit your own story for AI refinement |
| `/1` or `/2` | Pick a story option |
| `/ok` | Approve story or confirm upload |
| `/more` | Generate new story options |
| `/redo` | Skip current story or rebuild video |

#### Video Building
| Command | What It Does |
|---------|-------------|
| `/clips` | Start collecting custom video clips |
| `/done` | Finish collecting clips |
| `/build` | Build the video |
| `/rebuild` | Rebuild with different random effects |
| `/duration <N>` | Set duration (15-180s) or `auto` for 33-38s |
| `/trim_on` / `/trim_off` | Toggle auto-trim (removes last 6s from clips) |

#### YouTube
| Command | What It Does |
|---------|-------------|
| `/upload` | Upload to YouTube at next available slot |
| `/schedule` | View 4 daily upload time slots |
| `/stats` | Channel stats (subs, views, monetization progress) |

#### Bot Management
| Command | What It Does |
|---------|-------------|
| `/status` | Current bot state |
| `/resume` | Continue interrupted pipeline |
| `/stop` | Halt current long operation |
| `/reset` | Reset everything, start fresh |
| `/history` | View last 20 used stories |
| `/confirm` | Cleanup after successful upload |

#### Admin
| Command | What It Does |
|---------|-------------|
| `/add_user <id>` | Add user by Telegram ID |
| `/remove_user <id>` | Remove user |
| `/view_users` | List all allowed users |

#### Voice (ElevenLabs)
| Command | What It Does |
|---------|-------------|
| `/add_voice_key <key>` | Add ElevenLabs API key |
| `/voice_keys` | List all keys |
| `/remove_voice_key <N>` | Remove key by index |
| `/voice_api_status` | Live credit/quota check per key |
| `/voice elevenlabs` | Switch to ElevenLabs |
| `/voice edge` | Switch to Edge TTS |
| `/voice_id <id>` | Change voice ID |

---

## Upload Schedule

4 daily slots optimized for USA peak viewing (all times IST):

| Slot | IST | USA (EDT) | Target |
|------|-----|-----------|--------|
| 1 | 11:30 PM | 2:00 PM | Afternoon viewers |
| 2 | 2:30 AM | 5:00 PM | Pre-evening, algorithm indexes before 7 PM surge |
| 3 | 4:30 AM | 7:00 PM | Evening prime - peak Shorts feed + mobile |
| 4 | 6:30 AM | 9:00 PM | Late evening - post-dinner relaxation peak |

Videos upload as private 2-3 hours before slot time for algorithm indexing, then auto-publish at the scheduled time. Live countdown reminders are sent 3 hours before each slot with a color-coded progress bar.

---

## Algorithm Optimization (Based on Real Analytics)

| Factor | Optimization |
|--------|-------------|
| Duration | 33-38 seconds (our 33s = 1,310 views vs 52s = 30 views) |
| Hook | First sentence: shocking statement under 10 words |
| Structure | Hook -> Escalation -> Second Hook (15s mark) -> Twist -> CTA -> Loop |
| Loop Trick | Last line is open-ended cliffhanger - auto-replay makes viewer think story continues |
| 15s Gate | YouTube's sustained distribution gate - second hook placed here for retention |
| CTA | Only at the very end, before loop cliffhanger |
| SEO | Searchable title <50 chars, no emojis, 20 tags, 3 hashtags in desc |
| Upload | 2-3 hours before scheduled publish for algorithm indexing |
| Location | Metadata set to New York, USA |

---

## Folder Structure

```
ToldByNova/
+-- scripts/
|   +-- telegram_automation.py   # Main bot (5100+ lines)
|   +-- pipeline.py              # Video build pipeline (FFmpeg)
|   +-- voice_generator.py       # ElevenLabs + Edge TTS voice
|   +-- bot_service.py           # Auto-restart service wrapper
|   +-- upload_multilang_captions.py  # Batch caption uploader
+-- assets/
|   +-- bgm/                     # Background music (5 mood files)
|   |   +-- dramatic.mp3
|   |   +-- suspense.mp3
|   |   +-- emotional.mp3
|   |   +-- uplifting.mp3
|   |   +-- dark.mp3
|   +-- clips_default/           # Default video clips (5-10 clips)
|   +-- clips_manual/            # User-uploaded clips (auto-managed)
|   +-- channel/                 # Channel branding (logo, fonts)
|   |   +-- .env                 # Config: GitHub, lock doc, system IPs (gitignored)
|   |   +-- .env.example         # Template with placeholder values
|   +-- subscribe.mp4            # Subscribe overlay (green screen)
+-- data/                        # Runtime data (auto-created, gitignored)
|   +-- gdrive_token.json        # Google Drive OAuth (per-system, gitignored)
+-- output/                      # Built videos (auto-created, gitignored)
+-- credentials.json             # YouTube OAuth2 (gitignored)
+-- token.json                   # YouTube auth token (gitignored)
+-- .env.example                 # Environment variable template
+-- run_bot.example.bat          # Windows launcher template
+-- requirements.txt             # Python dependencies
```

---

## System Requirements

This bot runs on extremely basic hardware. All heavy processing (AI, voice) happens on cloud APIs. Your machine only runs Python + FFmpeg.

### Minimum (Will Work)

| Component | Spec |
|-----------|------|
| CPU | Any dual-core (even Intel i3 6th gen / Celeron) |
| RAM | 4 GB |
| Storage | 3 GB free |
| GPU | Not required (integrated graphics is fine) |
| Internet | Any stable connection |
| OS | Windows 10/11, Linux, macOS |
| Display | Any resolution (bot runs headless) |

### Tested & Confirmed Working On

| Component | Spec |
|-----------|------|
| CPU | Intel i5-7400 (4C/4T, 2017) |
| RAM | 16 GB DDR4 |
| GPU | Intel HD 630 (integrated, no dedicated GPU) |
| Storage | 256 GB SSD |
| OS | Windows 11 |

This exact system runs the bot 24/7 producing 4 videos/day with zero issues. FFmpeg video build takes ~30-60 seconds on CPU. If you have an NVIDIA GPU, FFmpeg uses it automatically for faster encoding.

**Bottom line:** If your PC can run Chrome, it can run this bot.

---

## All Telegram Commands (Detailed)

### Content Creation

| Command | Description | When to Use |
|---------|-------------|-------------|
| `/auto` | Generates an AI story using viral hook-first structure. AI searches DuckDuckGo for trending Reddit/viral stories, then creates a narration script with hook, escalation, twist, and loop cliffhanger. | When you want the bot to create a story from scratch |
| `/story <text>` | Submit your own story or idea. AI refines it into the optimal Shorts format with hooks, CTA, and loop ending. | When you have a specific story in mind |
| `/1` or `/2` | Pick one of the generated story options. | After `/auto` generates options |
| `/ok` | Approve the story (triggers voice + subtitle generation) or approve video for upload. Multi-purpose confirm button. | After reviewing story or preview |
| `/more` | Reject current options and generate fresh story options. | When none of the stories are good enough |
| `/redo` | Skip current story or request a video rebuild with new random effects. | When you want to start over |

### Video Building

| Command | Description | When to Use |
|---------|-------------|-------------|
| `/clips` | Enter clip collection mode. Send video files as documents or paste URLs. Bot shows a live progress counter. | After approving story, before building |
| `/done` | Finish collecting clips and move to build. | When you have enough clips |
| `/build` | Build the video with FFmpeg - assembles clips, narration, subtitles, BGM, subscribe overlay, vignette, and all effects. Multi-threaded (3-4 workers). | After story is approved (with or without custom clips) |
| `/rebuild` | Rebuild with different random effects - new subtitle colors, new clip order, new speed variations. Every rebuild is unique. | When preview doesn't look right |
| `/duration <N>` | Set fixed video duration in seconds (15-180). Use `/duration auto` for the optimal 33-38s range. | Before generating a story |
| `/trim_on` | Enable auto-trim: removes last 6 seconds from every clip (cuts RedNote/TikTok watermarks). Enabled by default. | When using clips from social media apps |
| `/trim_off` | Disable auto-trim. | When using clips without watermarks |
| `/clear_clip` | Delete all user-uploaded clips. | To start fresh with clips |

### YouTube Upload & Management

| Command | Description | When to Use |
|---------|-------------|-------------|
| `/upload` | Upload video to YouTube at the next available slot. Video goes as private and auto-publishes at scheduled time. Triggers all PRO features automatically. | After approving the preview |
| `/schedule` | View all 4 daily upload slots with times in IST and EDT. Shows which slots are used/available. | To plan your upload timing |
| `/stats` | Channel analytics - subscriber count, total views, video count, monetization progress (toward 1K subs + 10M Shorts views). | To check channel growth |
| `/confirm` | Cleanup after successful upload - deletes temp files, voice files, work directories, resets for next video. | After upload is confirmed |

### Bot Control

| Command | Description | When to Use |
|---------|-------------|-------------|
| `/start` or `/menu` | Show main menu with all available action buttons. | First time or anytime |
| `/status` | Current bot state - shows pipeline stage, clips count, stories used, voice engine, AI tool. | To check what's happening |
| `/resume` | Continue an interrupted pipeline from where it stopped (crash recovery). State is persistent. | After bot restart during a video |
| `/stop` | Gracefully halt current long operation (video build, upload). Stops after current segment, preserves state. | When you need to abort |
| `/reset` | Full reset - delete all temp files, reset state to IDLE, start fresh. | When something goes wrong |
| `/history` | View last 20 stories used (title, date, mood). | To check what was already used |

### Admin Commands

| Command | Description | When to Use |
|---------|-------------|-------------|
| `/add_user <telegram_id>` | Grant bot access to another user by their Telegram ID. | To let someone else use the bot |
| `/remove_user <telegram_id>` | Revoke access from a user. | To remove someone's access |
| `/view_users` | List all authorized users with names and IDs. | To see who has access |

### ElevenLabs Voice Management

| Command | Description | When to Use |
|---------|-------------|-------------|
| `/add_voice_key <key>` | Add an ElevenLabs API key. Auto-validates by hitting the API, shows account info, activates ElevenLabs engine. | When setting up voice accounts |
| `/voice_keys` | List all saved keys with index numbers and labels. | To see your keys |
| `/remove_voice_key <N>` | Remove a key by its index number (shown in `/voice_keys`). | When a key expires or you want to remove it |
| `/voice_api_status` | **Live real-time check** - hits every key's API, shows characters used/remaining, renewal date, progress bar, and estimated videos remaining per key. | To monitor quota usage |
| `/voice elevenlabs` | Switch voice engine to ElevenLabs (human-quality). | To activate ElevenLabs |
| `/voice edge` | Switch voice engine to Edge TTS (robotic but free and unlimited). | To switch back to free voice |
| `/voice` | Show current voice engine and settings. | To check active voice |
| `/voice_id <id>` | Change the ElevenLabs voice ID (get from elevenlabs.io voice settings). | To use a different voice |

### Multi-System Lock + Sync

| Command | Description | When to Use |
|---------|-------------|-------------|
| `/auth_drive` | One-time Google Drive OAuth. Bot sends you a URL, open in browser, authorize, paste the code back in chat. Enables data sync between systems. | First-time setup on each system |
| `/bot_lock` | Show instance lock status - this system's name, IPs, Google Doc status (who is ON/OFF), and Drive sync status. | To check which system is active |
| `/sync_now` | Force immediate sync of all data files to Google Drive (normally syncs every 10 seconds automatically). | When you want to push data right now before switching systems |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ffmpeg: command not found` | FFmpeg not in PATH. Add `C:\ffmpeg\bin` to system PATH |
| `BOT_TOKEN not set` | Set environment variables before running |
| Bot not responding | Check if bot is running. Check BOT_TOKEN is correct |
| `No clips found` | Add at least 1 clip to `assets/clips_default/` |
| `credentials.json not found` | Download from Google Cloud Console (Step 9d) |
| YouTube upload 403 | OAuth test user expired. Re-authorize (Step 9e) |
| ElevenLabs 429 error | Key quota exhausted. Bot auto-tries next key |
| All ElevenLabs keys exhausted | Bot auto-falls back to Edge TTS. Add more accounts next month |
| Duplicate bot messages | Kill all Python processes and restart bot once |
| Video too long | Use `/duration 35` or `/duration auto` for 33-38s |
| Story not USA-focused | AI prompt is pre-configured for USA. Custom stories via `/story` should be USA-relatable |
| Bot starts twice on reboot | Check Task Scheduler for duplicate tasks. Keep only one. |
| Bot shuts down immediately | Check Google Doc - your system might be set to OFF. Use `/bot_lock` to see status |
| Drive sync not working | Run `/auth_drive` first. Ensure Google Drive API is enabled in Cloud Console |
| "UNKNOWN" system detected | Your IP doesn't match any `system_NAME` in `.env`. Run `ipconfig` and update `.env` |
| Doc read failed (500 error) | Google rate-limits frequent requests. Bot auto-retries with backoff. Normal behavior |

---

## Contributing

Contributors are most welcome! If you want to help take this project to the next level, feel free to:

- Fork the repo and submit pull requests
- Report bugs or suggest features via Issues
- Improve the video pipeline, add new effects
- Add new AI providers or voice engines
- Optimize FFmpeg encoding or add new subtitle styles
- Improve SEO generation or algorithm optimization

All contributions are appreciated. Check the open issues for things to work on, or propose your own improvements.

---

## Support the Project

This software is **100% free and open source** under the [MIT License](LICENSE). You can use it, modify it, distribute it - no restrictions.

If this bot helps you get views and grow your channel, please consider subscribing to the original channel as a small thank you:

**[Subscribe to Told By Nova on YouTube](https://www.youtube.com/@ToldByNova?sub_confirmation=1)**

It costs nothing and means a lot. Thank you!

---

## License

MIT License - 100% free and open source.

You are free to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of this software. No restrictions, no royalties, no fees.

See [LICENSE](LICENSE) for full details.
