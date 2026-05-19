"""Voice generator: Edge TTS (Microsoft Emma Neural)"""
import asyncio, edge_tts, os

VOICE = "en-US-EmmaNeural"
RATE = "+8%"

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

def run(text, out_dir, prefix="voice", mood=None):
    try:
        asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, _edge_generate_async(text, out_dir, prefix)).result()
    except RuntimeError:
        return asyncio.run(_edge_generate_async(text, out_dir, prefix))

if __name__ == "__main__":
    import sys
    text = sys.argv[1] if len(sys.argv) > 1 else "This is a test voice generation."
    out = sys.argv[2] if len(sys.argv) > 2 else "."
    run(text, out)
