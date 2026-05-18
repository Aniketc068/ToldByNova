"""Download English captions from existing YT videos, translate via trexocli, upload."""
import json, sys, os, time, subprocess, shutil, tempfile
sys.stdout.reconfigure(encoding='utf-8')

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMP_DIR = f"{PROJECT}/output/temp_captions"
os.makedirs(TEMP_DIR, exist_ok=True)

TOKEN_PATH = "C:/Users/chatu/mcp-servers/youtube-mcp-server/token.json"
LANGUAGES = [("Spanish", "es"), ("French", "fr"), ("German", "de"), ("Portuguese", "pt")]
TREXOCLI = "C:/Users/chatu/AppData/Local/Programs/trexocli/trexocli.exe"
if not os.path.exists(TREXOCLI):
    TREXOCLI = "trexocli"


def get_youtube():
    with open(TOKEN_PATH) as f:
        td = json.load(f)
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    creds = Credentials(
        token=td["token"], refresh_token=td["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=td["client_id"], client_secret=td["client_secret"],
        scopes=td.get("scopes"))
    if creds.expired or not creds.valid:
        creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def _trexo_call(prompt, timeout=180):
    """Call trexocli, return result text or None."""
    tmp_dir = tempfile.mkdtemp()
    try:
        args = [TREXOCLI, "--output-format", "json", "--max-turns", "3", "-p", prompt]
        r = subprocess.run(args, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           timeout=timeout, cwd=tmp_dir, encoding='utf-8', errors='replace')
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or '')[-300:]
            print(f"    [trexo] rc={r.returncode}: {err}")
            return None
        stdout = r.stdout.strip()
        for line in stdout.split('\n'):
            line = line.strip()
            if line.startswith('{'):
                try:
                    data = json.loads(line)
                    result = data.get("result", "")
                    if result:
                        return result
                except json.JSONDecodeError:
                    pass
        return stdout if stdout else None
    except subprocess.TimeoutExpired:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"    [trexo] timeout ({timeout}s)")
        return None
    except FileNotFoundError:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"    [trexo] NOT FOUND at {TREXOCLI}")
        return None
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"    [trexo] error: {e}")
        return None


def _clean_srt(text):
    """Extract valid SRT content from AI response."""
    lines = text.strip().split('\n')
    cleaned = []
    started = False
    for line in lines:
        if not started and line.strip().isdigit():
            started = True
        if started:
            cleaned.append(line)
    return '\n'.join(cleaned) if len(cleaned) >= 4 else None


def trexo_translate(srt_content, target_lang):
    """Translate SRT via trexocli. Chunks large files (>8K chars)."""
    if len(srt_content) > 8000:
        blocks = srt_content.strip().split('\n\n')
        chunks, current, cur_len = [], [], 0
        for block in blocks:
            if cur_len + len(block) > 6000 and current:
                chunks.append('\n\n'.join(current))
                current, cur_len = [], 0
            current.append(block)
            cur_len += len(block) + 2
        if current:
            chunks.append('\n\n'.join(current))

        print(f"    Large SRT ({len(srt_content)} chars) -> {len(chunks)} chunks")
        parts = []
        for i, chunk in enumerate(chunks):
            print(f"    Chunk {i+1}/{len(chunks)}...", end=" ", flush=True)
            prompt = f"Translate this SRT subtitle chunk to {target_lang}. Keep ALL formatting (numbers, timestamps, blank lines). Only translate text. Output ONLY translated SRT.\n\n{chunk}"
            result = _trexo_call(prompt, timeout=120)
            if not result:
                print("FAILED")
                return None
            print("OK")
            parts.append(result.strip())
            time.sleep(2)
        return _clean_srt('\n\n'.join(parts))
    else:
        prompt = f"Translate this SRT subtitle file to {target_lang}. Keep ALL SRT formatting (sequence numbers, timestamps, blank lines). Only translate text lines. Output ONLY the translated SRT.\n\n{srt_content}"
        result = _trexo_call(prompt, timeout=180)
        return _clean_srt(result) if result else None


def main():
    yt = get_youtube()

    resp = yt.search().list(part="id,snippet", forMine=True, type="video", maxResults=50, order="date").execute()
    videos = resp.get("items", [])
    print(f"Found {len(videos)} videos\n")

    total_up, total_fail = 0, 0

    for v in videos:
        vid_id = v["id"]["videoId"]
        title = v["snippet"]["title"]
        print(f"{'='*60}")
        print(f"{vid_id} — {title}")

        try:
            caps = yt.captions().list(part="snippet", videoId=vid_id).execute()
        except Exception as e:
            print(f"  SKIP (captions error): {e}\n")
            continue

        existing = set()
        en_cap_id = None
        for c in caps.get("items", []):
            lang = c["snippet"]["language"]
            existing.add(lang)
            if lang == "en" and not en_cap_id:
                en_cap_id = c["id"]

        print(f"  Have: {existing}")
        needed = [(n, c) for n, c in LANGUAGES if c not in existing]
        if not needed:
            print(f"  All done! SKIP\n")
            continue
        if not en_cap_id:
            print(f"  No English caption — SKIP\n")
            continue

        print(f"  Need: {[n for n, _ in needed]}")

        try:
            srt_data = yt.captions().download(id=en_cap_id, tfmt="srt").execute()
            en_srt = srt_data.decode('utf-8') if isinstance(srt_data, bytes) else str(srt_data)
            print(f"  English SRT: {len(en_srt)} chars")
        except Exception as e:
            print(f"  SKIP (download failed): {e}\n")
            continue

        if len(en_srt.strip()) < 20:
            print(f"  SKIP (too short)\n")
            continue

        for lang_name, lang_code in needed:
            print(f"  -> {lang_name}...")
            translated = trexo_translate(en_srt, lang_name)
            if not translated:
                print(f"  {lang_name} FAILED")
                total_fail += 1
                continue

            temp_path = f"{TEMP_DIR}/{vid_id}_{lang_code}.srt"
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(translated)

            try:
                from googleapiclient.http import MediaFileUpload
                media = MediaFileUpload(temp_path, mimetype='application/x-subrip', resumable=False)
                yt.captions().insert(
                    part="snippet",
                    body={"snippet": {"videoId": vid_id, "language": lang_code, "name": lang_name, "isDraft": False}},
                    media_body=media
                ).execute()
                print(f"  {lang_name} UPLOADED!")
                total_up += 1
            except Exception as e:
                print(f"  {lang_name} upload FAILED: {e}")
                total_fail += 1
            finally:
                try: os.remove(temp_path)
                except: pass
            time.sleep(3)
        print()

    try: os.rmdir(TEMP_DIR)
    except: pass
    print(f"{'='*60}")
    print(f"DONE! Uploaded: {total_up} | Failed: {total_fail}")


if __name__ == "__main__":
    main()
