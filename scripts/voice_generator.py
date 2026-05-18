"""Voice generator: ElevenLabs (multi-key waterfall) + Edge TTS fallback"""
import asyncio, edge_tts, os, re, json, base64, urllib.request, urllib.error

VOICE = "en-US-EmmaNeural"
RATE = "+8%"

_PROJECT = os.environ.get("NOVA_PROJECT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_EL_CONFIG_PATH = f"{_PROJECT}/data/elevenlabs_config.json"
_EL_API = "https://api.elevenlabs.io/v1"

# Mood -> best free female voice mapping
_MOOD_VOICES = {
    "suspense":    ("pFZP5JQG7iQjIQuC4Bku", "Lily"),        # Velvety Actress — dark, dramatic
    "dark":        ("pFZP5JQG7iQjIQuC4Bku", "Lily"),
    "horror":      ("pFZP5JQG7iQjIQuC4Bku", "Lily"),
    "dramatic":    ("EXAVITQu4vr4xnSDxMaL", "Sarah"),       # Mature, Confident
    "revenge":     ("EXAVITQu4vr4xnSDxMaL", "Sarah"),
    "justice":     ("EXAVITQu4vr4xnSDxMaL", "Sarah"),
    "happy":       ("cgSgspJ2msm6clMCkdW9", "Jessica"),     # Playful, Bright, Warm
    "upbeat":      ("cgSgspJ2msm6clMCkdW9", "Jessica"),
    "funny":       ("cgSgspJ2msm6clMCkdW9", "Jessica"),
    "emotional":   ("XrExE9yKIg1WjnnlVkGX", "Matilda"),     # Warm, Professional (free)
    "sad":         ("XrExE9yKIg1WjnnlVkGX", "Matilda"),
    "heartfelt":   ("XrExE9yKIg1WjnnlVkGX", "Matilda"),
    "mysterious":  ("FGY2WhTYpPnrIDTdsKH5", "Laura"),       # Enthusiast, Quirky
    "twist":       ("FGY2WhTYpPnrIDTdsKH5", "Laura"),
}
_DEFAULT_VOICE = ("EXAVITQu4vr4xnSDxMaL", "Sarah")

# ============ CONFIG ============

def _load_el_config():
    try:
        with open(_EL_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

def _save_el_config(config):
    os.makedirs(os.path.dirname(_EL_CONFIG_PATH), exist_ok=True)
    with open(_EL_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

# ============ ELEVENLABS ============

def _el_api_call(endpoint, api_key, data=None, method="GET"):
    url = f"{_EL_API}/{endpoint}"
    headers = {"xi-api-key": api_key}
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    else:
        req = urllib.request.Request(url, headers=headers, method=method)
    resp = urllib.request.urlopen(req, timeout=120)
    return json.loads(resp.read().decode("utf-8"))

def _build_srt_from_alignment(alignment, srt_path):
    chars = alignment.get("characters", [])
    starts = alignment.get("character_start_times_seconds", [])
    ends = alignment.get("character_end_times_seconds", [])

    if not chars or not starts or not ends:
        return 0

    words = []
    current_word = []
    word_start = None
    word_end = None

    for i, ch in enumerate(chars):
        if ch == " " or ch == "\n":
            if current_word:
                w = "".join(current_word)
                if w.strip():
                    words.append((word_start, word_end, w))
                current_word = []
                word_start = None
                word_end = None
            continue
        if word_start is None:
            word_start = starts[i] if i < len(starts) else 0
        word_end = ends[i] if i < len(ends) else word_start
        current_word.append(ch)

    if current_word:
        w = "".join(current_word)
        if w.strip():
            words.append((word_start, word_end, w))

    with open(srt_path, "w", encoding="utf-8") as f:
        for idx, (s, e, w) in enumerate(words, 1):
            s_ms = s * 1000
            e_ms = e * 1000
            ss = f"{int(s_ms//3600000):02d}:{int((s_ms%3600000)//60000):02d}:{int((s_ms%60000)//1000):02d},{int(s_ms%1000):03d}"
            es = f"{int(e_ms//3600000):02d}:{int((e_ms%3600000)//60000):02d}:{int((e_ms%60000)//1000):02d},{int(e_ms%1000):03d}"
            f.write(f"{idx}\n{ss} --> {es}\n{w}\n\n")

    return len(words)

def _el_generate(text, out_dir, prefix, config, mood=None):
    # Mood-based voice selection (overrides config voice_id)
    if mood and mood.lower() in _MOOD_VOICES:
        voice_id, voice_name = _MOOD_VOICES[mood.lower()]
        print(f"[ElevenLabs] Mood '{mood}' -> Voice: {voice_name}")
    else:
        voice_id = config.get("voice_id", _DEFAULT_VOICE[0])
        voice_name = config.get("voice_name", _DEFAULT_VOICE[1])
        print(f"[ElevenLabs] Voice: {voice_name}")
    model_id = config.get("model_id", "eleven_multilingual_v2")
    keys = config.get("keys", [])

    if not keys:
        return None

    for i, key_info in enumerate(keys):
        api_key = key_info.get("key", "")
        label = key_info.get("label", f"Key {i+1}")
        try:
            print(f"[ElevenLabs] Trying {label}...")
            endpoint = f"text-to-speech/{voice_id}/with-timestamps"
            data = {
                "text": text,
                "model_id": model_id,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75
                }
            }
            result = _el_api_call(endpoint, api_key, data=data)

            audio_b64 = result.get("audio_base64", "")
            alignment = result.get("alignment", {})

            if not audio_b64:
                print(f"[ElevenLabs] {label}: No audio in response")
                continue

            mp3 = f"{out_dir}/{prefix}.mp3"
            srt = f"{out_dir}/{prefix}.srt"

            with open(mp3, "wb") as f:
                f.write(base64.b64decode(audio_b64))

            n_words = _build_srt_from_alignment(alignment, srt)

            if os.path.getsize(mp3) < 1000:
                print(f"[ElevenLabs] {label}: Audio too small")
                os.remove(mp3)
                continue

            print(f"[ElevenLabs] OK via {label} | Words: {n_words} | MP3: {mp3}")
            return mp3, srt, n_words

        except urllib.error.HTTPError as e:
            code = e.code
            print(f"[ElevenLabs] {label}: HTTP {code}")
            if code in (401, 403):
                print(f"[ElevenLabs] {label}: Invalid/expired key, skipping")
            elif code == 429:
                print(f"[ElevenLabs] {label}: Quota exceeded, trying next")
            else:
                body = e.read().decode("utf-8", errors="replace")[:200]
                print(f"[ElevenLabs] {label}: Error {code}: {body}")
            continue
        except Exception as e:
            print(f"[ElevenLabs] {label}: Error: {e}")
            continue

    print("[ElevenLabs] All keys exhausted")
    return None

# ============ EDGE TTS ============

async def _edge_generate_async(text, out_dir, prefix):
    mp3 = f"{out_dir}/{prefix}.mp3"
    srt = f"{out_dir}/{prefix}.srt"

    communicate = edge_tts.Communicate(text, VOICE, rate=RATE)
    communicate.tts_config.boundary = "WordBoundary"

    words = []
    audio_chunks = []

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            offset_ms = chunk["offset"] / 10000
            duration_ms = chunk["duration"] / 10000
            w = chunk["text"]
            if w.strip():
                words.append((offset_ms, offset_ms + duration_ms, w))

    with open(mp3, "wb") as f:
        for c in audio_chunks:
            f.write(c)

    with open(srt, "w", encoding="utf-8") as f:
        for i, (s, e, w) in enumerate(words, 1):
            ss = f"{int(s//3600000):02d}:{int((s%3600000)//60000):02d}:{int((s%60000)//1000):02d},{int(s%1000):03d}"
            es = f"{int(e//3600000):02d}:{int((e%3600000)//60000):02d}:{int((e%60000)//1000):02d},{int(e%1000):03d}"
            f.write(f"{i}\n{ss} --> {es}\n{w}\n\n")

    print(f"[EdgeTTS] Voice: {mp3} | Words: {len(words)} | SRT: {srt}")
    return mp3, srt, len(words)

def _edge_generate(text, out_dir, prefix="voice"):
    try:
        asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, _edge_generate_async(text, out_dir, prefix)).result()
    except RuntimeError:
        return asyncio.run(_edge_generate_async(text, out_dir, prefix))

# ============ MAIN ============

def run(text, out_dir, prefix="voice", mood=None):
    config = _load_el_config()
    if config and config.get("engine") == "elevenlabs" and config.get("keys"):
        result = _el_generate(text, out_dir, prefix, config, mood=mood)
        if result:
            return result
        print("[Voice] All ElevenLabs keys exhausted, falling back to Edge TTS")
    return _edge_generate(text, out_dir, prefix)

if __name__ == "__main__":
    import sys
    text = sys.argv[1] if len(sys.argv) > 1 else "This is a test voice generation."
    out = sys.argv[2] if len(sys.argv) > 2 else "."
    run(text, out)
