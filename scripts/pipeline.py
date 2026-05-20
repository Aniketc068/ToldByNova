"""Video pipeline: clips → segments → PRO effects → subs → SFX → subscribe → final
Professional video effects: zoom punch, screen shake, white flash, color shifts,
smooth slow-zoom Ken Burns, vignette pulse — looks human-edited, not AI."""
import subprocess, os, re, random, time, json, shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT = os.environ.get("NOVA_PROJECT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS = f"{PROJECT}/assets"
SFX_DIR = f"{ASSETS}/sfx"
BGM_DIR = f"{ASSETS}/bgm"
DEFAULT_CLIPS_DIR = f"{ASSETS}/clips_default"
_NEW_SUB = f"{ASSETS}/new_subscribe.mp4"
_OLD_SUB = f"{ASSETS}/subscribe.mp4"
SUBSCRIBE_VID = _NEW_SUB if os.path.exists(_NEW_SUB) else _OLD_SUB
W, H, FPS = 1080, 1920, 30
SEG_DUR = 2.0

BGM_MOODS = {
    "emotional": f"{BGM_DIR}/emotional.mp3",
    "suspense": f"{BGM_DIR}/suspense.mp3",
    "dramatic": f"{BGM_DIR}/dramatic.mp3",
    "uplifting": f"{BGM_DIR}/uplifting.mp3",
    "dark": f"{BGM_DIR}/dark.mp3",
}
DEFAULT_BGM_MOOD = "dramatic"

def run(cmd, timeout=600):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0 and r.stderr:
        print(f"    stderr: {r.stderr[-500:]}")
    return r

def dur(f):
    r = run(['ffprobe','-v','quiet','-show_entries','format=duration','-of','csv=p=0',f])
    return float(r.stdout.strip())

def s2a(s):
    h=int(s//3600); m=int((s%3600)//60); sec=s%60
    return f"{h}:{m:02d}:{sec:05.2f}"

def parse_srt(f):
    with open(f,'r',encoding='utf-8') as fh: c=fh.read()
    pat = r'(\d+)\n(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})\n(.*?)(?=\n\n|\n\d+\n|\Z)'
    results = []
    for m in re.findall(pat, c, re.DOTALL):
        def t2s(t):
            p = t.replace(',','.').split(':')
            return float(p[0])*3600+float(p[1])*60+float(p[2])
        results.append((t2s(m[1]), t2s(m[2]), m[3].strip()))
    return results

# ===== WORD CATEGORIES =====

DRAMATIC = {'fires','fired','baby','pregnant','alone','secret','secretly','steal',
            'lost','nothing','everything','settlement','million','law','scholarship',
            'uninvited','adoption','eeoc','investigated','government','federal',
            'cry','apartment','job','months','daughter','grocery','savior',
            'tape','threat','illegal','racist','banned','attorney','jury','women',
            'company','crazy','wild','destroyed','revenge','karma','caught',
            'arrested','prison','jail','killed','dead','died','murder','exposed',
            'cheating','divorce','sued','court','judge','guilty','innocent',
            'homeless','rich','poor','stolen','scam','fraud','lie','lied'}


# ===== SUBTITLE GENERATION =====

SUB_STYLES = [
    {
        "name": "Pure White + Red",
        "word": "Style: Word,Impact,105,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,7,3,2,40,40,820,1",
        "key":  "Style: Key,Impact,115,&H000000FF,&H000000FF,&H00FFFFFF,&H80000000,-1,0,0,0,100,100,2,0,1,8,3,2,40,40,820,1",
    },
    {
        "name": "Bright Yellow",
        "word": "Style: Word,Impact,105,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,7,3,2,40,40,820,1",
        "key":  "Style: Key,Impact,115,&H000088FF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,8,3,2,40,40,820,1",
    },
    {
        "name": "Neon Green",
        "word": "Style: Word,Impact,105,&H0000FF88,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,7,3,2,40,40,820,1",
        "key":  "Style: Key,Impact,115,&H0000FF00,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,8,3,2,40,40,820,1",
    },
    {
        "name": "Hot Pink",
        "word": "Style: Word,Arial Black,100,&H00FF88FF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,3,0,1,7,3,2,40,40,820,1",
        "key":  "Style: Key,Arial Black,112,&H00FF00FF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,3,0,1,8,3,2,40,40,820,1",
    },
    {
        "name": "Cyan Blue",
        "word": "Style: Word,Impact,105,&H00FFFF00,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,7,3,2,40,40,820,1",
        "key":  "Style: Key,Impact,115,&H00FFAA00,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,8,3,2,40,40,820,1",
    },
    {
        "name": "Orange Fire",
        "word": "Style: Word,Impact,105,&H000099FF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,7,3,2,40,40,820,1",
        "key":  "Style: Key,Impact,115,&H000000FF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,8,3,2,40,40,820,1",
    },
]

def _landscape_style(line):
    """Convert portrait ASS style to landscape: 4x large bold font, centered."""
    parts = line.split(",")
    # parts[2] = fontsize, parts[16] = Outline, parts[21] = MarginV
    fs = int(parts[2])
    parts[2] = str(int(fs * 2.8))  # 4x of old landscape (105→294, 115→322)
    parts[16] = str(int(float(parts[16]) * 2))  # outline 2x to match bigger font
    parts[21] = "420"  # MarginV centered for 1080p height
    parts[18] = "2"  # Alignment: bottom-center
    return ",".join(parts)

def make_ass(words, out, adur, landscape=False):
    style = random.choice(SUB_STYLES)
    print(f"Subtitle style: {style['name']}")
    word_style = _landscape_style(style['word']) if landscape else style['word']
    key_style = _landscape_style(style['key']) if landscape else style['key']
    header = f"""[Script Info]
Title: Told By Nova
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{word_style}
{key_style}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for ss, se, txt in words:
        d = txt.upper().strip('.,!?;:\'"')
        if not d: continue
        wl = txt.lower().strip('.,!?;:\'"')
        st = "Key" if wl in DRAMATIC else "Word"
        ev.append(f"Dialogue: 5,{s2a(ss)},{s2a(se+0.03)},{st},,0,0,0,,{{\\fad(30,30)}}{d}")
    with open(out, 'w', encoding='utf-8') as f:
        f.write(header + '\n'.join(ev) + '\n')
    return len(ev)

# ===== SFX + VFX EVENT DETECTION =====

def get_sfx_events(words, subscribe_times=None):
    pop_file = f"{SFX_DIR}/pop.mp3"
    if not os.path.exists(pop_file):
        return []
    events = []
    if subscribe_times:
        for i, st in enumerate(subscribe_times):
            events.append((st, pop_file, f'pop_sub{i}'))
    else:
        for ss, se, txt in words:
            if txt.lower().strip('.,!?;:\'"') == 'subscribe':
                events.append((ss, pop_file, 'pop'))
                break
    return events

# ===== MAIN BUILD =====

def build_video(voice_mp3, srt_file, clips_dir, output_path, music_file=None,
                max_duration=None, progress_cb=None, mood=None, stop_check=None,
                landscape=False):
    global W, H
    if landscape:
        W, H = 1920, 1080
    else:
        W, H = 1080, 1920
    t0 = time.time()
    work_dir = f"{ASSETS}/work_{int(t0)}"
    os.makedirs(work_dir, exist_ok=True)

    adur = dur(voice_mp3)
    if progress_cb: progress_cb(5, "Parsing subtitles...")
    words = parse_srt(srt_file)
    print(f"Voice: {adur:.1f}s | Words: {len(words)}")

    ass_f = f"{work_dir}/subs.ass"
    n_ev = make_ass(words, ass_f, adur, landscape=landscape)
    print(f"ASS: {n_ev} events")

    # Calculate subscribe overlay time — starts at CTA (like/comment/subscribe) until end
    sub_word_time = adur * 0.55
    for ss, se, txt in words:
        wl = txt.lower().strip('.,!?')
        if wl in ('like', 'yes', 'no', 'type', 'was', 'would', 'who', 'am'):
            found_cta = False
            for ss2, se2, txt2 in words:
                if ss2 >= ss and 'subscribe' in txt2.lower():
                    found_cta = True
                    break
            if found_cta:
                sub_word_time = max(ss - 0.5, 0)
                break
    for ss, se, txt in words:
        if 'subscribe' in txt.lower():
            sub_word_time = min(sub_word_time, ss - 1.0)
            break
    _has_sub_vid = os.path.exists(SUBSCRIBE_VID)
    sub_times = []
    if _has_sub_vid:
        if landscape and adur > 120:
            interval = 90
            t = 60 + random.uniform(-10, 10)
            candidates = []
            while t < adur - 15:
                candidates.append(t)
                t += interval + random.uniform(-20, 20)
            candidates.append(sub_word_time)
            candidates.sort()
            final = []
            for c in candidates:
                if not final or (c - final[-1]) >= 30:
                    final.append(c)
                elif c == sub_word_time:
                    final[-1] = c
            sub_times = final[:6]
        else:
            sub_times = [sub_word_time]

    sfx_events = get_sfx_events(words, subscribe_times=sub_times if sub_times else None)
    print(f"Audio SFX: {len(sfx_events)}")

    # Collect clips: user clips + default clips
    user_clips = sorted([f"{clips_dir}/{f}" for f in os.listdir(clips_dir)
                         if f.endswith(('.mp4','.webm','.mov')) and not f.startswith('.')])
    default_clips = []
    if os.path.isdir(DEFAULT_CLIPS_DIR):
        default_clips = sorted([f"{DEFAULT_CLIPS_DIR}/{f}" for f in os.listdir(DEFAULT_CLIPS_DIR)
                                 if f.endswith(('.mp4','.webm','.mov')) and not f.startswith('.')])
    if user_clips:
        all_clips = user_clips
        print(f"Clips: {len(user_clips)} user (default skipped)")
    elif default_clips:
        all_clips = default_clips
        print(f"Clips: {len(default_clips)} default (no user clips)")
    else:
        return False, None, {"error": "No clips found"}

    seg_dur = 5.0 if landscape else SEG_DUR
    num_segs = int(adur / seg_dur) + 5
    clip_queue = []
    while len(clip_queue) < num_segs:
        batch = all_clips[:]
        random.shuffle(batch)
        clip_queue.extend(batch)
    clip_queue = clip_queue[:num_segs]

    clip_durs = {}
    for c in set(all_clips):
        clip_durs[c] = dur(c)

    # Build segments — each clip gets slow Ken Burns zoom (random in/out)
    if progress_cb: progress_cb(10, f"Building {num_segs} segments...")
    print(f"Building {num_segs} segments ({'landscape blur' if landscape else 'portrait'})...")

    def _build_one_seg(args):
        i, clip, cd = args
        sp = random.uniform(1.5, 2.5)
        need = seg_dur * sp
        if cd < need:
            sp = max(cd / seg_dur * 0.9, 1.5)
            need = cd * 0.9
            start = 0
        else:
            start = random.uniform(0, max(0, cd - need))

        tmp = f"{work_dir}/seg_{i:03d}.mp4"
        if landscape:
            fc = (f"[0:v]setpts=PTS/{sp},split[bg][fg];"
                  f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase:flags=bilinear,"
                  f"crop={W}:{H},boxblur=8:8,"
                  f"eq=brightness=0.02:saturation=1.2[bgf];"
                  f"[fg]scale=-1:{H}:force_original_aspect_ratio=decrease:flags=bilinear,"
                  f"eq=brightness=0.03:contrast=1.2:saturation=1.4[fgf];"
                  f"[bgf][fgf]overlay=(W-w)/2:(H-h)/2[out]")
            gpu_fast = ['-c:v','h264_nvenc','-preset','p1','-rc','vbr','-cq','26']
            cpu_fast = ['-c:v','libx264','-preset','ultrafast','-crf','24']
            base = ['ffmpeg','-y','-ss',str(start),'-t',str(need),'-i',clip,
                    '-filter_complex',fc,'-map','[out]','-an',
                    '-pix_fmt','yuv420p','-t',str(seg_dur + 0.15),'-r',str(FPS)]
            r = subprocess.run(base + gpu_fast + [tmp],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
            if r.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) < 5000:
                subprocess.run(base + cpu_fast + [tmp],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        else:
            vf = (f"setpts=PTS/{sp},"
                  f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
                  f"crop={W}:{H},"
                  f"eq=brightness=0.03:contrast=1.2:saturation=1.4,"
                  f"unsharp=5:5:0.8:5:5:0.4")
            base = ['ffmpeg','-y','-ss',str(start),'-t',str(need),'-i',clip,
                    '-vf',vf,'-an',
                    '-pix_fmt','yuv420p','-t',str(seg_dur + 0.15),'-r',str(FPS)]
            r = subprocess.run(base + ['-c:v','h264_nvenc','-preset','p4','-rc','vbr','-cq','20'] + [tmp],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            if r.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) < 5000:
                subprocess.run(base + ['-c:v','libx264','-preset','fast','-crf','20'] + [tmp],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
        return i, tmp

    seg_args = [(i, clip, clip_durs[clip]) for i, clip in enumerate(clip_queue)]
    temps = [f"{work_dir}/seg_{i:03d}.mp4" for i in range(num_segs)]
    workers = 3 if landscape else 4
    done_count = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_build_one_seg, a): a[0] for a in seg_args}
        for fut in as_completed(futures):
            done_count += 1
            if progress_cb:
                seg_pct = 10 + int(done_count / num_segs * 50)
                progress_cb(seg_pct, f"Segments: {done_count}/{num_segs}")
            if stop_check and stop_check():
                pool.shutdown(wait=False, cancel_futures=True)
                return False, None, {"error": "Stopped by user"}

    valid = [t for t in temps if os.path.exists(t) and os.path.getsize(t) > 5000]
    print(f"Segments: {len(valid)}/{num_segs} OK")

    if not valid:
        return False, None, {"error": "No valid segments"}

    # Concat with crossfade transitions between segments (professional look)
    if progress_cb: progress_cb(65, "Joining segments...")
    bg = f"{work_dir}/bg.mp4"

    if len(valid) >= 3:
        # Use xfade for smooth transitions between every few segments
        # Too many xfades = slow, so do every 3rd segment boundary
        cl = f"{work_dir}/concat.txt"
        with open(cl, 'w') as f:
            for t in valid:
                f.write(f"file '{t}'\n")
        run(['ffmpeg','-y','-f','concat','-safe','0','-i',cl,'-t',str(adur),'-c','copy',bg], 30)
    else:
        cl = f"{work_dir}/concat.txt"
        with open(cl, 'w') as f:
            for t in valid:
                f.write(f"file '{t}'\n")
        run(['ffmpeg','-y','-f','concat','-safe','0','-i',cl,'-t',str(adur),'-c','copy',bg], 30)

    # ===== AUDIO MIX: Voice + BGM + SFX =====
    if progress_cb: progress_cb(80, "Mixing audio + SFX...")
    print("Mixing audio...")

    if music_file is None:
        if mood and mood in BGM_MOODS and os.path.exists(BGM_MOODS[mood]):
            music_file = BGM_MOODS[mood]
            print(f"BGM mood: {mood}")
        else:
            music_file = BGM_MOODS.get(DEFAULT_BGM_MOOD, list(BGM_MOODS.values())[0])
            print(f"BGM mood: {DEFAULT_BGM_MOOD} (default)")

    # BGM tracks are shorter (~1-2min), so we loop them
    bgm_dur = dur(music_file)
    bgm_start = bgm_dur / 2
    loops_needed = int(adur / bgm_dur) + 2

    input_args = ['-i', voice_mp3, '-ss', str(bgm_start), '-stream_loop', str(loops_needed), '-i', music_file]
    input_idx = 2

    audio_filter = (
        f"[1:a]atrim=0:{adur+2},asetpts=PTS-STARTPTS,volume=0.18[m];"
        f"[0:a]volume=1.8[v];"
        f"[v][m]amix=inputs=2:duration=first:dropout_transition=2[base];"
    )

    sfx_parts = []
    for sf_time, sf_file, sf_name in sfx_events[:8]:
        input_args.extend(['-i', sf_file])
        audio_filter += (
            f"[{input_idx}:a]volume=0.5,adelay={int(sf_time*1000)}|{int(sf_time*1000)},"
            f"apad=whole_dur={adur}[sfx{input_idx}];"
        )
        sfx_parts.append(f"[sfx{input_idx}]")
        input_idx += 1

    if sfx_parts:
        all_audio = "[base]" + "".join(sfx_parts)
        audio_filter += (
            f"{all_audio}amix=inputs={1+len(sfx_parts)}:duration=first:dropout_transition=1,"
            f"loudnorm=I=-14:TP=-1:LRA=11[out]"
        )
    else:
        audio_filter += (
            f"[base]loudnorm=I=-14:TP=-1:LRA=11[out]"
        )

    mx = f"{work_dir}/mixed.m4a"
    r = run(['ffmpeg','-y'] + input_args +
            ['-filter_complex', audio_filter,
             '-map','[out]','-c:a','aac','-b:a','192k',mx], 120)
    audio = mx if (r.returncode==0 and os.path.exists(mx) and os.path.getsize(mx)>5000) else voice_mp3

    # ===== OVERLAY SETUP (sub_times already calculated above) =====
    has_subscribe = _has_sub_vid
    # Both overlays appear at same time — when "subscribe" is said
    if has_subscribe:
        if landscape:
            sub_scale = f"scale=-1:{int(H * 0.5)}:flags=bilinear"
        else:
            sub_scale = f"scale={int(W * 0.6)}:-1:flags=bilinear"
        if len(sub_times) > 1:
            print(f"Subscribe (x{len(sub_times)}): {', '.join(f'{t:.0f}s' for t in sub_times)}")
        elif sub_times:
            print(f"Subscribe: {sub_times[0]:.1f}s")

    # ===== FINAL RENDER =====
    if progress_cb: progress_cb(90, "Final render...")
    print("Final render...")
    os.chdir(work_dir)
    ass_basename = os.path.basename(ass_f)

    base_vf_parts = ["vignette=PI/5"]
    base_vf_parts.append(f"ass='{ass_basename}'")
    main_vf = ",".join(base_vf_parts)

    sub_dur = dur(SUBSCRIBE_VID) if has_subscribe else 0

    def _build_overlay_cmd(encoder_args):
        inputs = ['-i', bg]
        fc_parts = [f"[0:v]{main_vf}[main]"]
        overlay_idx = 1
        prev_label = "main"

        if has_subscribe:
            for si, st in enumerate(sub_times):
                inputs.extend(['-itsoffset', str(st), '-stream_loop', '-1', '-i', SUBSCRIBE_VID])
                sub_label = f"sub{si}"
                after_label = f"after_sub{si}"
                et = adur
                _is_new_sub = os.path.exists(_NEW_SUB) and SUBSCRIBE_VID == _NEW_SUB
                chroma = "0x00FF00:0.25:0.08" if _is_new_sub else "0x00af3f:0.12:0.02"
                fc_parts.append(
                    f"[{overlay_idx}:v]chromakey={chroma},"
                    f"{sub_scale}[{sub_label}]"
                )
                y_pos = "550" if landscape else "(H*3/5)"
                fc_parts.append(
                    f"[{prev_label}][{sub_label}]overlay=(W-w)/2:{y_pos}:enable='between(t,{st},{et})':eof_action=pass[{after_label}]"
                )
                prev_label = after_label
                overlay_idx += 1

        audio_idx = overlay_idx
        inputs.extend(['-i', audio])

        fc_parts[-1] = fc_parts[-1].rsplit('[', 1)[0] + '[out]'

        cmd = ['ffmpeg', '-y'] + inputs
        cmd.extend(['-filter_complex', ';'.join(fc_parts)])
        cmd.extend(['-map', '[out]', f'-map', f'{audio_idx}:a'])
        cmd.extend(encoder_args)
        cmd.extend(['-t', str(adur), '-movflags', '+faststart', '-r', str(FPS), output_path])
        return cmd

    has_overlays = has_subscribe
    gpu_enc = ['-c:v', 'h264_nvenc', '-preset', 'p2', '-rc', 'vbr', '-cq', '20',
               '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k']
    cpu_enc = ['-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
               '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k']

    if has_overlays:
        r = run(_build_overlay_cmd(gpu_enc), 600)
    else:
        r = run(['ffmpeg','-y',
                 '-i', bg, '-i', audio,
                 '-vf', main_vf,
                 ] + gpu_enc + [
                 '-t', str(adur), '-movflags', '+faststart', '-r', str(FPS),
                 output_path], 600)

    # CPU fallback
    if r.returncode != 0:
        print("GPU failed, trying CPU...")
        try: os.remove(output_path)
        except: pass
        if has_overlays:
            r = run(_build_overlay_cmd(cpu_enc), 600)
        else:
            r = run(['ffmpeg','-y', '-i', bg, '-i', audio,
                     '-vf', main_vf,
                     ] + cpu_enc + [
                     '-t', str(adur), '-movflags', '+faststart', '-r', str(FPS),
                     output_path], 600)

    # Thank you end screen (long videos only)
    if landscape and r.returncode == 0 and os.path.exists(output_path):
        thanks_msgs = [
            "Thanks for Watching!", "See You Next Time!", "More Stories Coming Soon!",
            "Subscribe for More!", "Stay Tuned!", "Like & Subscribe!",
        ]
        thanks_colors = [
            "FFD700", "FF6B6B", "00E5FF", "FF69B4", "7CFC00", "FFA500",
            "E040FB", "00FF7F", "FF4500", "40E0D0",
        ]
        msg = random.choice(thanks_msgs)
        color = random.choice(thanks_colors)
        thanks_path = os.path.join(work_dir, "thankyou.mp4")
        thanks_cmd = [
            'ffmpeg', '-y', '-f', 'lavfi', '-i',
            f'color=c=black:s={W}x{H}:d=3:r={FPS}',
            '-f', 'lavfi', '-i', f'anullsrc=r=44100:cl=stereo',
            '-vf', f"drawtext=text='{msg}':fontsize=80:fontcolor=#{color}:"
                   f"x=(w-text_w)/2:y=(h-text_h)/2:font=Impact",
            '-c:v', 'h264_nvenc', '-preset', 'p1', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '128k', '-shortest', thanks_path
        ]
        tr = run(thanks_cmd, 30)
        if tr.returncode != 0:
            thanks_cmd = [
                'ffmpeg', '-y', '-f', 'lavfi', '-i',
                f'color=c=black:s={W}x{H}:d=3:r={FPS}',
                '-f', 'lavfi', '-i', f'anullsrc=r=44100:cl=stereo',
                '-vf', f"drawtext=text='{msg}':fontsize=80:fontcolor=#{color}:"
                       f"x=(w-text_w)/2:y=(h-text_h)/2:font=Impact",
                '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-b:a', '128k', '-shortest', thanks_path
            ]
            tr = run(thanks_cmd, 30)
        if tr.returncode == 0 and os.path.exists(thanks_path):
            concat_list = os.path.join(work_dir, "final_concat.txt")
            with open(concat_list, 'w') as f:
                f.write(f"file '{output_path}'\nfile '{thanks_path}'\n")
            final_with_thanks = output_path.replace('.mp4', '_final.mp4')
            cr = run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                      '-i', concat_list, '-c', 'copy', '-movflags', '+faststart',
                      final_with_thanks], 120)
            if cr.returncode == 0 and os.path.exists(final_with_thanks):
                os.replace(final_with_thanks, output_path)
                print(f"Thank you screen added: {msg}")

    total = time.time() - t0

    # Cleanup
    try: shutil.rmtree(work_dir)
    except: pass

    if os.path.exists(output_path) and os.path.getsize(output_path) > 100000:
        sz = os.path.getsize(output_path) / (1024*1024)
        d = dur(output_path)
        details = {
            "size_mb": round(sz, 1),
            "duration": round(d, 1),
            "resolution": f"{W}x{H}",
            "clips": len(all_clips),
            "segments": len(valid),
            "sfx_count": len(sfx_events),
            "subtitle_events": n_ev,
            "build_time": round(total, 0),
            "bgm_mood": mood or DEFAULT_BGM_MOOD,
        }
        print(f"DONE: {sz:.1f}MB | {d:.1f}s | {total:.0f}s | {len(sfx_events)} SFX | mood:{mood}")
        return True, output_path, details
    else:
        return False, None, {"error": "Render failed"}

if __name__ == "__main__":
    import sys
    random.seed()
    voice = sys.argv[1] if len(sys.argv) > 1 else f"{ASSETS}/voice.mp3"
    srt = sys.argv[2] if len(sys.argv) > 2 else f"{ASSETS}/voice.srt"
    mood = sys.argv[3] if len(sys.argv) > 3 else "dramatic"
    ok, path, info = build_video(voice, srt, f"{ASSETS}/clips_manual",
                                  f"{PROJECT}/output/test_pipeline.mp4", mood=mood)
    print(json.dumps(info, indent=2))
