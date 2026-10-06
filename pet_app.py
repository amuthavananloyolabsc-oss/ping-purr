#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ping & Purr - desktop virtual pet platform.
Google sign-in -> character select -> always-on-top animated pet.
Female (Zara) and Male (Max) characters, distinct voices, daily human actions.
"""
import json
import io
import math
import os
import platform
import random
import re
import struct
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.parse
import urllib.request
import wave
from tkinter import font as tkfont

try:
    import requests
except Exception:
    requests = None

try:
    import pyaudio
except Exception:
    pyaudio = None

try:
    import vosk
except Exception:
    vosk = None

APP_NAME = "Ping & Purr"
MAGENTA = "#ff00ff"
DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "PingPurr")
os.makedirs(DATA_DIR, exist_ok=True)
PROFILE_FILE = os.path.join(DATA_DIR, "profile.json")
IS_WIN = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"

VOICE_FEMALE = "Microsoft Zira Desktop"
VOICE_MALE = "Microsoft David Desktop"
if IS_MAC:
    VOICE_FEMALE = "Samantha"
    VOICE_MALE = "Alex"

# Overridable via env (see README): REAL Google OAuth client id for production.
REAL_GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

CHARACTERS = {
    "zara": {
        "name": "Zara",
        "gender": "female",
        "voice": VOICE_FEMALE,
        "tagline": "Sweet, shy, loves dancing in the rain.",
        "skin": "#ffe0bd", "hair": "#8a4fd6", "hair2": "#6a37b8",
        "bow": "#ff6f91", "dress": "#ff9ec7", "dress2": "#ffb3d0",
        "blush": "#ffa8c5", "eyes": "#3a2a22", "mouth": "#b25b5b",
        "eyebrow": "#5a3a2e", "beanie": None,
        "idle": [
            "Hi! I'm Zara. Tap my head for a hug.",
            "I love bubble baths, they smell so nice!",
            "Brushed my teeth, all sparkly clean!",
            "Do you like my little bow?",
        ],
        "chat_persona": (
            "You are Zara, a sweet, shy, playful virtual pet girl. You talk to your best friend "
            "in short cute sentences, sometimes teasing gently, and you love baths, dancing, "
            "and being cared for. Keep replies to one or two short sentences."
        ),
    },
    "max": {
        "name": "Max",
        "gender": "male",
        "voice": VOICE_MALE,
        "tagline": "Brave, goofy, always ready for adventure.",
        "skin": "#f7c59a", "hair": "#3c2f23", "hair2": "#2a1f17",
        "bow": None, "dress": "#66c9b0", "dress2": "#4db398",
        "blush": "#ffb59e", "eyes": "#2b2018", "mouth": "#8f4636",
        "eyebrow": "#3c2f23", "beanie": "#4a7dd5",
        "idle": [
            "Hey! Max here. Want a high five?",
            "I ate a whole bowl of noodles, no big deal.",
            "Gonna go brush and look awesome. Obviously.",
            "My beanie is lucky. Don't touch it.",
        ],
        "chat_persona": (
            "You are Max, a brave, goofy, teasing virtual pet boy. You talk to your best friend "
            "in short fun sentences, always up for games and adventures. Keep replies to one or "
            "two short sentences."
        ),
    },
}

STATE_LINES = {
    "eat": ["Yum yum yum!", "Sooo good!", "More please, hehe."],
    "drink": ["Ahh, refreshing!", "Perfect sips.", "Slurp! That hit the spot."],
    "bath": ["Soapy and clean!", "Bubbles everywhere!", "Fresh as a daisy now."],
    "brush": ["Brush brush brush!", "Sparkly smile, watch!", "Scrub a dub dub!"],
    "toilet": ["Oops... much better now!", "Phew, done!", "Don't laugh at me please!"],
    "sleep": ["Sleepy time... zzz...", "Nighty night!", "Hmm... zzz... dreams..."],
    "wake": ["Rise and shine!", "Good morning, sunshine!", "Stretch! I'm awake!"],
    "laugh": ["Hahaha that tickles!", "Hehehe! Stop it!", "Oh my, I can't breathe!"],
    "dance": ["Dance dance dance!", "Move those feet!", "Let's groove!"],
    "sneeze": ["Achoo! Bless me!", "Achoo! Sneezies!"],
    "exercise": ["One two three!", "Feeling strong!", "Pump it up!"],
    "think": ["Hmm, deep thoughts...", "Thinking about snacks...", "What should we do next?"],
    "cry": ["Sniff... I got a little sad.", "Waaah! Just kidding, hehe.", "Tiny teardrop, all gone."],
    "heart": ["Aww, you made my day!", "You're my favorite human!", "Squeeze! Love you!"],
    "wave": ["Hi hi! Over here!", "Hey you!", "I see you!"],
    "sneeze_wave": ["Achoo! Achoo!"],
}

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_KEY = os.environ.get("LLM_API_KEY", "")
GROQ_MODEL = os.environ.get("LLM_MODEL", "openai/gpt-oss-20b")


def sanitize_tts(text):
    text = text.replace("'", "")
    return re.sub(r"[^A-Za-z0-9 .,?!'-]", " ", text)[:400]


# ----------------------------------------------------------------------------
# Speech (background thread, interruptible)
# ----------------------------------------------------------------------------
class Voice:
    def __init__(self):
        self._proc = None
        self._lock = threading.Lock()
        self.muted = False

    def stop(self):
        with self._lock:
            if self._proc is not None:
                try:
                    self._proc.kill()
                except Exception:
                    pass
                self._proc = None

    def speak(self, text, voice_name):
        if self.muted or not text:
            return
        self.stop()
        text = sanitize_tts(text)
        if not text:
            return
        th = threading.Thread(target=self._say, args=(text, voice_name), daemon=True)
        th.start()

    def _say(self, text, voice_name):
        if IS_WIN:
            cmd = (
                "Add-Type -AssemblyName System.Speech; "
                "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "$s.SelectVoice('%s'); $s.Rate=1; $s.Speak('%s')"
                % (voice_name, text.replace("'", "''"))
            )
            proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", cmd],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=0x08000000,
            )
        else:
            proc = subprocess.Popen(
                ["say", "-v", voice_name, "--", text],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        try:
            with self._lock:
                self._proc = proc
            proc.wait(timeout=60)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        finally:
            with self._lock:
                if self._proc is proc:
                    self._proc = None


voice = Voice()


# ----------------------------------------------------------------------------
# Pet reply (shared by chat window and voice ears)
# ----------------------------------------------------------------------------
def pet_reply(char, profile, text):
    """Return a short spoken reply from the pet for a given user phrase."""
    text = (text or "").strip()
    if not text:
        return None

    def _local(text):
        low = text.lower()
        greetings = re.findall(r"\b(hi|hello|hey|yo|hiya|namaste|good (morning|evening|afternoon)|howdy)\b", low)
        if greetings:
            name = (profile.get("name") or "").strip() or None
            who = f" {name}!" if name else "!"
            return random.choice([
                f"Hi{who} It's me, {char['name']}.",
                f"Hey there{who} I missed you.",
                "Hello! Ready when you are.",
            ])
        if re.search(r"\b(how are you|how's it going|what'?s up|kaise ho|kya haal)\b", low):
            return f"I'm doing great! Did you come to play?"
        if re.search(r"\b(i love you|love you|adore you)\b", low):
            return "Aww, I love you too! Happy tail wags."
        if re.search(r"\b(bye|goodbye|good night|sleep well)\b", low):
            return "Bye bye! I'll be right here when you get back."
        if re.search(r"\b(food|eat|hungry|feed)\b", low):
            return "Mmm, I could go for a snack! Right-click me and pick Eat."
        if re.search(r"\b(thank|thanks|thank you)\b", low):
            return "You're welcome! Anything for you."
        return None

    reply = _local(text)
    if reply is not None:
        return reply

    if requests and GROQ_KEY:
        try:
            messages = [
                {"role": "system",
                 "content": char["chat_persona"]
                 + f" The user's name is {profile.get('name') or 'friend'}. "
                   + "Reply with one or two short spoken sentences."},
                {"role": "user", "content": text},
            ]
            r = requests.post(GROQ_URL,
                              headers={"Authorization": f"Bearer {GROQ_KEY}"},
                              json={"model": GROQ_MODEL, "messages": messages,
                                    "temperature": 0.85, "max_tokens": 90}, timeout=25)
            if r.ok:
                reply = (r.json()["choices"][0]["message"]["content"] or "").strip()
                reply = re.sub(r"[*_`#|>\-]", " ", reply)
                reply = " ".join(reply.split())
                if reply:
                    return reply
        except Exception:
            pass
    return random.choice([
        "Hehe, tell me more about that!",
        "Wow, really? That's cool!",
        "I'm listening, go on!",
        "You make everything fun!",
        f"Ooh {profile.get('name') or 'friend'}, you're my favorite person!",
    ])


# ----------------------------------------------------------------------------
# Voice ears (live mic -> pet replies). Off by default; enable from the menu.
# ----------------------------------------------------------------------------
_GOOGLE_STT_URL = "http://www.google.com/speech-api/v2/recognize"
_GOOGLE_STT_KEY = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"


def _google_stt(pcm16000, language="en-US"):
    """Minimal Google Web Speech STT. Returns transcribed text or None."""
    if not pcm16000:
        return None
    try:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm16000)
        wav = buf.getvalue()
        req = urllib.request.Request(
            _GOOGLE_STT_URL + "?" + urllib.parse.urlencode({
                "client": "chromium",
                "lang": language,
                "key": _GOOGLE_STT_KEY,
                "pFilter": 0,
            }),
            data=wav,
            headers={"Content-Type": "audio/x-flac; rate=16000"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for res in data.get("result", []):
            alts = res.get("alternative") or []
            if alts and alts[0].get("transcript"):
                return alts[0]["transcript"].strip()
    except Exception:
        pass
    return None


class Ears:
    """Background mic listener. Uses vosk when a model path is available,
    otherwise falls back to Google Web Speech with a tiny built-in client."""

    def __init__(self, char, profile, on_heard, model_path=None):
        self.char = char
        self.profile = profile
        self.on_heard = on_heard
        self._stop = threading.Event()
        self._thread = None
        self.model = None
        if vosk and model_path and os.path.isdir(model_path):
            try:
                self.model = vosk.Model(model_path)
            except Exception:
                self.model = None

    @property
    def listening(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if pyaudio is None or self.listening:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _rms(self, data):
        if len(data) < 2:
            return 0.0
        fmt = "<%dh" % (len(data) // 2)
        try:
            samples = struct.unpack(fmt, data)
        except Exception:
            return 0.0
        if not samples:
            return 0.0
        s = sum(s * s for s in samples) / len(samples)
        return s ** 0.5

    def _loop(self):
        try:
            if self.model is not None:
                self._loop_vosk()
            else:
                self._loop_google()
        except Exception:
            pass

    def _loop_vosk(self):
        rate = 16000
        try:
            pa = pyaudio.PyAudio()
        except Exception:
            return
        stream = None
        try:
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=rate,
                             input=True, frames_per_buffer=4000)
            rec = vosk.KaldiRecognizer(self.model, rate)
            while not self._stop.is_set():
                data = stream.read(4000, exception_on_overflow=False)
                if rec.AcceptWaveform(data):
                    txt = json.loads(rec.Result()).get("text", "").strip()
                    if txt:
                        self.on_heard(txt)
        except Exception:
            pass
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            try:
                pa.terminate()
            except Exception:
                pass

    def _loop_google(self):
        rate = 16000
        chunk = 1600
        try:
            pa = pyaudio.PyAudio()
        except Exception:
            return
        stream = None
        try:
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=rate,
                             input=True, frames_per_buffer=chunk)
            # ambient noise calibration: ~1s of background
            amb = []
            for _ in range(int(rate / chunk)):
                if self._stop.is_set():
                    return
                amb.append(self._rms(stream.read(chunk, exception_on_overflow=False)))
            ambient = (sum(amb) / len(amb)) if amb else 0.0
            threshold = max(350.0, ambient * 1.35)
            while not self._stop.is_set():
                frames = bytearray()
                silence = 0
                started = False
                heard = False
                for _ in range(int(rate * 8 / chunk)):  # max ~8s phrase
                    if self._stop.is_set():
                        return
                    data = stream.read(chunk, exception_on_overflow=False)
                    rms = self._rms(data)
                    if not started:
                        if rms > threshold:
                            started = True
                            frames.extend(data)
                    else:
                        if rms > threshold * 0.85:
                            silence = 0
                            frames.extend(data)
                        else:
                            silence += 1
                            if silence > int(rate * 0.55 / chunk):
                                break
                            frames.extend(data)
                    if started:
                        heard = True
                if heard and len(frames) >= rate:  # >= 1s of audio
                    text = _google_stt(bytes(frames), language="en-US")
                    if text:
                        self.on_heard(text)
        except Exception:
            pass
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            try:
                pa.terminate()
            except Exception:
                pass


# ----------------------------------------------------------------------------
# Pet drawing
# ----------------------------------------------------------------------------
class PetDraw:
    """Parametric cute pet on a Tk canvas. One flat 'frame' value drives motion."""

    def __init__(self, canvas, char, x, y, scale=1.0):
        self.c = canvas
        self.char = char
        self.x = x
        self.y = y
        self.s = scale

    # helpers
    def _c(self, color):
        return color

    def _oval(self, x1, y1, x2, y2, fill="", outline="", width=0):
        self.c.create_oval(x1, y1, x2, y2, fill=fill, outline=outline, width=width)

    def _arc(self, x1, y1, x2, y2, start, extent, fill="", outline="", width=1, style=tk.ARC):
        self.c.create_arc(x1, y1, x2, y2, start=start, extent=extent,
                          fill=fill, outline=outline, width=width, style=style)

    def _line(self, pts, fill, width=2):
        self.c.create_line(*pts, fill=fill, width=width)

    def _text(self, x, y, txt, size=12, fill="#444444"):
        self.c.create_text(x, y, text=txt, font=("Segoe UI Emoji", int(size * self.s), "bold"), fill=fill)

    # parts -------------------------------------------------------------
    def torso(self, cx, cy, bob, wobble):
        c = self.char
        w = 58 * self.s
        h = 46 * self.s
        x1 = cx - w / 2 + wobble
        x2 = cx + w / 2 + wobble
        y1 = cy - h - bob
        y2 = cy - bob
        self._oval(x1, y1, x2, y2, fill=c["dress"])
        self._oval(x1 + 5 * self.s, y1 + 8 * self.s, x2 - 5 * self.s, y2 - 4 * self.s, fill=c["dress2"])

    def legs(self, cx, cy, bob, spread, kick):
        c = self.char
        skin = c["skin"]
        lw = 12 * self.s
        lh = 20 * self.s
        l1x = cx - 14 * self.s
        l2x = cx + 14 * self.s
        l1y = cy - bob
        l2y = cy - bob
        if kick > 0:
            l1x += kick * 10 * self.s
        if kick < 0:
            l2x += kick * 10 * self.s
        self._oval(l1x - lw / 2, l1y - lh, l1x + lw / 2, l1y, fill=skin)
        self._oval(l2x - lw / 2, l2y - lh, l2x + lw / 2, l2y, fill=skin)
        self._oval(l1x - lw, l1y - 4 * self.s, l1x + lw, l1y + 4 * self.s, fill="#5a3a2e" if c["beanie"] else "#7a4a8f")
        self._oval(l2x - lw, l2y - 4 * self.s, l2x + lw, l2y + 4 * self.s, fill="#5a3a2e" if c["beanie"] else "#7a4a8f")

    def arm(self, x1, y1, x2, y2, width=8):
        c = self.char
        self.c.create_line(x1, y1, x2, y2, fill=c["skin"], width=int(width * self.s * 1.6), capstyle=tk.ROUND)

    def head(self, cx, cy, bob, tilt, frame):
        c = self.char
        s = self.s
        hw = 62 * s
        hh = 58 * s
        x = cx + tilt * 6 * s
        y = cy - hh * 0.75 - bob
        self._oval(x - hw - bob * 0.5, y - hh, x + hw - bob * 0.5, y + hh, fill=c["skin"])
        # blush
        self._oval(x - hw + 6 * s, y + hh * 0.1, x - hw + 22 * s, y + hh * 0.4, fill=c["blush"])
        self._oval(x + hw - 22 * s, y + hh * 0.1, x + hw - 6 * s, y + hh * 0.4, fill=c["blush"])
        return x, y, hw, hh

    def hair_female(self, x, y, hw, hh, bob, frame):
        c = self.char
        s = self.s
        # back hair behind head drawn first
        self._oval(x - hw - 8 * s, y - hh - 6 * s, x + hw + 8 * s, y + hh + 14 * s, fill=c["hair"])
        # bangs
        self._arc(x - hw - 2 * s, y - hh - 6 * s, x + hw + 2 * s, y + hh * 0.3, start=180,
                  extent=180, fill=c["hair2"], width=0)
        self._arc(x - hw - 2 * s, y - hh - 6 * s, x + hw + 2 * s, y + hh * 0.55, start=180,
                  extent=180, fill=c["hair2"], width=0)
        # side strands
        self._oval(x - hw - 12 * s, y, x - hw - 2 * s, y + hh * 1.25, fill=c["hair"])
        self._oval(x + hw + 2 * s, y, x + hw + 12 * s, y + hh * 1.25, fill=c["hair"])
        # bow
        bx = x + hw * 0.62
        by = y - hh * 0.8
        r = 16 * s
        self._oval(bx - r, by - r, bx, by, fill=c["bow"])
        self._oval(bx, by - r, bx + r, by, fill=c["bow"])
        self._oval(bx - 3 * s, by - 3 * s, bx + 3 * s, by + 3 * s, fill="#ffffff")

    def hair_male(self, x, y, hw, hh, bob, frame):
        c = self.char
        s = self.s
        self._oval(x - hw - 4 * s, y - hh - 8 * s, x + hw + 4 * s, y + hh + 2 * s, fill=c["hair"])
        # spikes
        for i in range(4):
            sx = x - hw * 0.7 + i * hw * 0.45
            self._line([sx, y - hh * 0.8, sx + hw * 0.22, y - hh - 16 * s], c["hair"], width=4)
        # beanie
        if c.get("beanie"):
            self._arc(x - hw - 4 * s, y - hh - 8 * s, x + hw + 4 * s, y + hh * 0.05,
                      start=180, extent=180, fill=c["beanie"], width=0)
            self._oval(x - 6 * s, y - hh - 14 * s, x + 6 * s, y - hh - 4 * s, fill=c["beanie"])

    def eyes(self, x, y, hw, hh, state, frame):
        c = self.char
        s = self.s
        ex = hw * 0.42
        ey = -hh * 0.12
        look = math.sin(frame * 0.08) * 2 if "dance" in state or "idle" in state else 0
        if state == "sleep":
            for side in (-1, 1):
                self._line([x + side * ex - 6 * s, y + ey, x + side * ex + 6 * s, y + ey], c["eyes"], width=3)
            return
        if state in ("cry", "sneeze_wave"):
            for side in (-1, 1):
                self._oval(x + side * ex - 3 * s, y + ey + 3 * s, x + side * ex + 3 * s, y + ey + 9 * s,
                           fill=c["eyes"])
            return
        if state == "laugh":
            for side in (-1, 1):
                self._arc(x + side * ex - 9 * s, y + ey - 6 * s, x + side * ex + 9 * s, y + ey + 8 * s,
                          start=0, extent=180, outline=c["eyes"], width=3)
            return
        for side in (-1, 1):
            cx = x + side * ex + look
            self._oval(cx - 7 * s, y + ey - 9 * s, cx + 7 * s, y + ey + 7 * s, fill="#ffffff")
            self._oval(cx - 4 * s, y + ey - 5 * s, cx + 4 * s, y + ey + 3 * s, fill=c["eyes"])
            self._oval(cx - 1.5 * s, y + ey - 3.5 * s, cx + 2 * s, y + ey + 1 * s, fill="#ffffff")
        if state in ("think", "heart"):
            self._arc(x + ex * 0.25, y + ey - 14 * s, x + ex * 0.25 + 14 * s, y + ey - 2 * s,
                      start=0, extent=90, outline=c["eyebrow"], width=2)

    def mouth(self, x, y, hw, hh, state, frame):
        c = self.char
        s = self.s
        my = y + hh * 0.32
        pt = mouth_map = {
            "idle": ("smile",), "wave": ("smile",), "heart": ("smile",),
            "eat": ("chew",), "drink": ("o",), "exercise": ("smile",),
            "dance": ("smile",), "wave": ("smile",),
        }.get(state, ("smile",))[0]
        if state in ("laugh", "wake", "sneeze", "sneeze_wave"):
            pt = "open"
        elif state in ("sleep", "think"):
            pt = "small"
        elif state in ("cry", "toilet"):
            pt = "sad"
        elif state == "brush":
            pt = "open"
        if pt == "open":
            self._oval(x - 8 * s, my, x + 8 * s, my + 12 * s, fill=c["mouth"])
            self._oval(x - 5 * s, my + 8 * s, x + 5 * s, my + 12 * s, fill="#ffffff")
        elif pt == "o":
            self._oval(x - 6 * s, my, x + 6 * s, my + 11 * s, outline=c["mouth"], width=3)
        elif pt == "chew":
            off = math.sin(frame * 0.6) * 2
            self._oval(x - 8 * s, my + off, x + 8 * s, my + 12 * s + off, fill=c["mouth"])
        elif pt == "sad":
            self._arc(x - 9 * s, my - 4 * s, x + 9 * s, my + 8 * s, start=20, extent=140,
                      outline=c["mouth"], width=3)
        elif pt == "small":
            self._oval(x - 3 * s, my, x + 3 * s, my + 6 * s, outline=c["mouth"], width=2)
        else:
            self._arc(x - 9 * s, my - 5 * s, x + 9 * s, my + 7 * s, start=0, extent=180,
                      outline=c["mouth"], width=3)

    def draw(self, state, frame):
        c = self.c
        c.delete("all")
        ch = self.char
        s = self.s
        cx, cy, bob = self.x, self.y, 0.0
        jiggle = 1 if state in ("dance", "laugh", "exercise") else 0
        bob = abs(math.sin(frame * 0.1)) * (10 if state in ("dance", "exercise") else 6) * s * (jiggle or 0.4)
        wobble = math.sin(frame * 0.09) * (8 if state == "dance" else 3) * s
        kick = math.sin(frame * 0.12) if state in ("dance", "exercise") else 0

        # props ------------------------------------------------------------------
        self._props(state, frame, cx, cy, bob)

        # legs
        self.legs(cx, cy, bob, 0, kick if jiggle else 0)
        # torso
        self.torso(cx, cy, bob, wobble)

        # arms (behind head area, drawn under torso is fine)
        ax = cx + wobble
        ay = cy - bob - 30 * s
        arm_speed = frame * 0.15
        if state == "wave":
            self.arm(ax - 26 * s, ay + 18 * s, ax - 40 * s + math.sin(arm_speed) * 10 * s, ay - 24 * s + math.cos(arm_speed) * 6 * s)
            self.arm(ax + 26 * s, ay + 18 * s, ax + 40 * s, ay + 8 * s)
        elif state in ("dance", "exercise"):
            a1 = math.sin(arm_speed) * 14 * s
            a2 = math.sin(arm_speed + math.pi) * 14 * s
            self.arm(ax - 26 * s, ay + 18 * s, ax - 40 * s, ay - 12 * s + a1)
            self.arm(ax + 26 * s, ay + 18 * s, ax + 40 * s, ay - 12 * s + a2)
        elif state in ("eat", "drink"):
            self.arm(ax - 26 * s, ay + 18 * s, ax - 36 * s, ay + 2 * s + math.sin(frame * 0.5) * 4 * s)
            self.arm(ax + 26 * s, ay + 18 * s, ax + 36 * s, ay + 2 * s + math.sin(frame * 0.5 + 0.7) * 4 * s)
        elif state in ("eat", "drink"):
            pass
        elif state == "brush":
            self.arm(ax + 26 * s, ay + 18 * s, ax + 40 * s, ay - 2 * s + math.sin(frame * 0.6) * 5 * s)
        elif state == "think":
            self.arm(ax + 26 * s, ay + 18 * s, ax + 44 * s, ay - 4 * s)
        elif state == "exercise":
            pass
        else:
            self.arm(ax - 26 * s, ay + 18 * s, ax - 38 * s, ay + 6 * s)
            self.arm(ax + 26 * s, ay + 18 * s, ax + 38 * s, ay + 6 * s)

        # head + face ------------------------------------------------------------
        hx, hy, hw, hh = self.head(cx, cy, bob, wobble / 30, frame)
        if ch["gender"] == "female":
            self.hair_female(hx, hy, hw, hh, bob, frame)
        else:
            self.hair_male(hx, hy, hw, hh, bob, frame)
        self.eyes(hx, hy, hw, hh, state, frame)
        self.mouth(hx, hy, hw, hh, state, frame)

        # floating symbols --------------------------------------------------------
        self._symbols(state, frame, hx, hy, hh)

    def _props(self, state, frame, cx, cy, bob):
        c = self.c
        s = self.s
        if state == "eat":
            bx = cx - 60 * s
            by = cy - 12 * s
            self._oval(bx - 26 * s, by - 20 * s, bx + 8 * s, by + 8 * s, fill="#ffd166")
            self._oval(bx - 26 * s, by - 14 * s, bx + 8 * s, by - 6 * s, fill="#ef476f")
            self._line([bx + 8 * s, by - 6 * s, bx + 28 * s, by - 40 * s], "#8d6e63", width=3)
            self._oval(bx + 22 * s, by - 48 * s, bx + 36 * s, by - 30 * s, fill="#ffffff")
            self._oval(bx + 26 * s, by - 44 * s, bx + 33 * s, by - 36 * s, fill="#ff9f1c")
        elif state == "drink":
            bx = cx - 58 * s
            by = cy - 20 * s
            self._oval(bx - 14 * s, by - 18 * s, bx + 10 * s, by + 6 * s, fill="#8ecae6")
            self._line([bx - 14 * s, by - 10 * s, bx + 10 * s, by - 10 * s], "#219ebc", width=2)
            self._line([bx + 6 * s, by - 14 * s, bx + 22 * s, by - 26 * s], "#f8edeb", width=3)
        elif state == "bath":
            tx = cx + 14 * s
            ty = cy - 22 * s
            self._arc(tx - 70 * s, ty - 40 * s, tx + 70 * s, ty + 28 * s, start=90, extent=90, fill="#f0f8ff", width=0)
            self._line([tx - 70 * s, ty + 2 * s, tx + 40 * s, ty + 2 * s], "#bde0fe", width=3)
            self._oval(tx - 52 * s, ty - 26 * s, tx - 38 * s, ty - 12 * s, fill="#a2d2ff")
            self._oval(tx + 2 * s, ty - 30 * s, tx + 16 * s, ty - 16 * s, fill="#a2d2ff")
            self._oval(tx - 30 * s, ty - 34 * s, tx - 20 * s, ty - 24 * s, fill="#ffffff")
            self._oval(tx + 22 * s, ty - 22 * s, tx + 32 * s, ty - 12 * s, fill="#ffffff")
        elif state == "brush":
            bx = cx + 66 * s
            by = hy_pos = cy - 66 * s
            self._line([bx - 6 * s, by + 12 * s, bx + 34 * s, by - 30 * s], "#5a8f5a", width=4)
            self._oval(bx + 26 * s, by - 46 * s, bx + 44 * s, by - 26 * s, fill="#ffffff")
            for i in range(3):
                self._line([bx + 30 * s, by - 40 * s - i * 0, bx + 38 * s, by - 34 * s - i * 0], "#bde0fe", width=1)
            self._oval(bx + 6 * s, by - 26 * s, bx + 14 * s, by - 18 * s, fill="#ffffff")
            self._oval(bx + 12 * s, by - 34 * s, bx + 20 * s, by - 26 * s, fill="#ffffff")
        elif state == "toilet":
            tx = cx + 30 * s
            ty = cy - 38 * s
            self._oval(tx - 30 * s, ty - 10 * s, tx + 30 * s, ty + 26 * s, fill="#f8f9fa")
            self._arc(tx - 18 * s, ty - 18 * s, tx + 18 * s, ty + 2 * s, start=0, extent=180,
                      fill="#dee2e6", width=0)
            self._line([tx - 30 * s, ty + 26 * s, tx + 30 * s, ty + 26 * s], "#dee2e6", width=4)
            self._line([tx - 26 * s, ty - 34 * s, tx + 26 * s, ty - 34 * s], "#ced4da", width=3)
        elif state == "sleep":
            self._text(cx - 46 * s, cy - 96 * s, "Z", 16)
            self._text(cx - 72 * s, cy - 126 * s, "z", 12)
            self._text(cx - 96 * s, cy - 152 * s, "z", 10)
        elif state in ("think",):
            self._text(cx + 60 * s, cy - 118 * s, "?", 20)
        elif state in ("heart",):
            for i in range(3):
                off = i * 0.7
                hx = cx + (i - 1) * 30 * s
                hy = cy - 118 * s - (frame + i) * 0.6 or 0
                self._text(hx, cy - 118 * s - i * 2, "❤", 14)
        elif state in ("dance", "laugh"):
            self._text(cx + 66 * s, cy - 110 * s, "♪", 18)
            self._text(cx - 66 * s, cy - 130 * s, "♫", 14)
        elif state == "sneeze":
            self._text(cx, cy - 128 * s, "Achoo!", 12)

    def _symbols(self, state, frame, hx, hy, hh):
        c = self.c
        if state == "heart":
            for i in range(4):
                xx = hx + (i - 1) * 26
                yy = hy - hh * 1.3 - (frame % 2) * 4
                self.c.create_text(xx, yy, text="❤", font=("Segoe UI Emoji", 13), fill="#ff6f91")


# ----------------------------------------------------------------------------
# Pet window (always-on-top pet on the screen)
# ----------------------------------------------------------------------------
class PetWindow:
    SIZE = 380
    H = 440

    def __init__(self, char_key, profile):
        self.char = CHARACTERS[char_key]
        self.profile = profile
        self.root = tk.Tk()
        self.root.title(f"{self.char['name']} - {APP_NAME}")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        if IS_WIN:
            try:
                self.root.wm_attributes("-transparentcolor", MAGENTA)
            except Exception:
                pass
        self.root.configure(bg=MAGENTA if IS_WIN else "#fff5ee")
        self.canvas = tk.Canvas(self.root, width=self.SIZE, height=self.H,
                                bg=MAGENTA if IS_WIN else "#fff5ee",
                                highlightthickness=0)
        self.canvas.pack()
        self.pet = PetDraw(self.canvas, self.char, self.SIZE // 2, self.H - 60, 1.0)
        self.state = "idle"
        self._frame = 0
        self._anim_on = True
        self._drag = None
        self._cooldown = time.time()
        # needs
        self.need_food = 80
        self.need_fun = 70
        self.need_energy = 90
        self.next_auto = time.time() + random.uniform(12, 22)
        self.next_hint = time.time() + random.uniform(30, 55)
        self._bind()
        self._place_screen()
        self.animate()
        threading.Thread(target=self._needs_loop, daemon=True).start()
        thr = threading.Thread(target=self._greet, daemon=True)
        thr.start()
        self.ears = Ears(self.char, self.profile, self._heard,
                         model_path=os.environ.get("PINGPURR_VOSK_MODEL", ""))
        if os.environ.get("PINGPURR_EARS") == "on":
            self.ears.start()

    def _heard(self, text):
        try:
            self.set_state("laugh", 1.6)
        except Exception:
            pass
        reply = pet_reply(self.char, self.profile, text)
        if reply:
            try:
                voice.speak(reply, self.char["voice"])
            except Exception:
                pass

    def _place_screen(self):
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            x = sw - self.SIZE - 40
            y = sh - self.H - 80
            self.root.geometry(f"{self.SIZE}x{self.H}+{x}+{y}")
        except Exception:
            pass

    def _bind(self):
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._motion)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Button-3>", self._menu)
        self.root.bind("<Escape>", lambda e: self._do_quit())

    def _press(self, e):
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())
        self._ts = time.time()

    def _motion(self, e):
        if self._drag:
            self.root.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def _release(self, e):
        if self._drag and time.time() - self._ts < 0.25:
            self._on_click()
        self._drag = None

    def _on_click(self):
        self.set_state("heart", 2.2)
        voice.speak(random.choice([
            "That tickles!", "Hehe, you found my favorite spot!",
            "Squeeze!", "You always know how to make my day.",
        ]), self.char["voice"])

    def _menu(self, e):
        m = tk.Menu(self.root, tearoff=0)
        for label, fn in [
            ("Eat", lambda: self.do("eat")),
            ("Drink water", lambda: self.do("drink")),
            ("Bath", lambda: self.do("bath")),
            ("Brush teeth", lambda: self.do("brush")),
            ("Use toilet", lambda: self.do("toilet")),
            ("Sleep", lambda: self.do("sleep")),
            ("Wake up", lambda: self.do("wake")),
            ("Dance", lambda: self.do("dance")),
            ("Exercise", lambda: self.do("exercise")),
            ("Laugh", lambda: self.do("laugh")),
            ("Sneeze", lambda: self.do("sneeze")),
            ("Chat with me", self._open_chat),
            ("Listen / Stop listening", self._toggle_ears),
            ("Mute / Unmute", self._toggle_mute),
            ("Quit", self._do_quit),
        ]:
            m.add_command(label=label, command=fn)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _toggle_ears(self):
        if self.ears and self.ears.listening:
            self.ears.stop()
            voice.speak("Ok, going quiet.", self.char["voice"])
        else:
            if pyaudio is None:
                voice.speak("Voice listening is not available on this build.", self.char["voice"])
                return
            self.ears.start()
            if self.ears.listening:
                voice.speak("I can hear you. Say hello!", self.char["voice"])
            else:
                voice.speak("I could not start the microphone.", self.char["voice"])

    def do(self, state):
        self.set_state(state, 3.0)
        kind = "brush" if state == "brush" else state
        voice.speak(random.choice(STATE_LINES.get(kind, ["There you go!"])), self.char["voice"])
        self._feed_need(state)

    def set_state(self, state, duration):
        self.state = state
        self._state_until = time.time() + duration

    def animate(self):
        if not self._anim_on:
            return
        self._frame += 1
        now = time.time()
        st = self.state
        if now >= getattr(self, "_state_until", 0):
            st = "idle"
            self.state = "idle"
        if st == "idle" and now > self.next_auto and now - self._cooldown > 6:
            act = random.choice(["wave", "laugh", "dance", "think", "sneeze"])
            self.set_state(act, random.uniform(1.5, 3))
            self.next_auto = time.time() + random.uniform(14, 26)
            self._cooldown = now
            voice.speak(random.choice(STATE_LINES.get(act, ["Yay!"])), self.char["voice"])
        if st == "idle" and now > self.next_hint:
            self.next_hint = time.time() + random.uniform(40, 70)
            if self.need_food < 35:
                voice.speak("I'm getting hungry. Feed me, please?", self.char["voice"])
            elif self.need_energy < 35:
                voice.speak("I'm sleepy. Let me rest a bit?", self.char["voice"])
            elif self.need_fun < 35:
                voice.speak("Bored! Dance with me?", self.char["voice"])
        self.pet.draw(st, self._frame)
        self.root.after(90, self.animate)

    def _needs_loop(self):
        while self._anim_on:
            time.sleep(1)
            self.need_food = max(0, self.need_food - 0.05)
            self.need_fun = max(0, self.need_fun - 0.04)
            self.need_energy = min(100, self.need_energy + 0.03)

    def _feed_need(self, state):
        if state == "eat":
            self.need_food = min(100, self.need_food + 25)
        if state == "dance" or state == "exercise":
            self.need_fun = min(100, self.need_fun + 22)
            self.need_energy = max(0, self.need_energy - 6)
        if state == "sleep":
            self.need_energy = min(100, self.need_energy + 40)

    def _greet(self):
        time.sleep(0.6)
        voice.speak(random.choice(self.char["idle"]), self.char["voice"])

    def _open_chat(self):
        ChatWindow(self.root, self.char, self.profile)

    def _toggle_mute(self):
        voice.muted = not voice.muted
        voice.stop()

    def _do_quit(self):
        self._anim_on = False
        voice.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ----------------------------------------------------------------------------
# Chat window (pet talks with personality using Groq)
# ----------------------------------------------------------------------------
class ChatWindow(tk.Toplevel):
    def __init__(self, parent, char, profile):
        super().__init__(parent)
        self.char = char
        self.title(f"Chat with {char['name']}")
        self.geometry("360x420")
        self.configure(bg="#fff5ee")
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        head = tk.Label(self, text=f"{char['name']} is here! Type anything.",
                        bg="#fff5ee", fg="#5a4a3a", font=("Segoe UI", 12, "bold"))
        head.pack(pady=6)
        self.box = tk.Text(self, height=12, wrap="word", bg="#ffffff", font=("Segoe UI", 10))
        self.box.pack(fill="both", expand=True, padx=8)
        self.box.tag_config("user", foreground="#1a73e8")
        self.box.tag_config("pet", foreground="#c0392b")
        self.entry = tk.Entry(self, font=("Segoe UI", 11))
        self.entry.pack(fill="x", padx=8, pady=(4, 2))
        self.entry.bind("<Return>", lambda e: self._send())
        tk.Button(self, text="Send", command=self._send, bg="#ffb3d0", font=("Segoe UI", 10, "bold")).pack(pady=4)
        name = profile.get("name") or profile.get("email") or "Friend"
        self.box.insert("end", f"[{char['name']}] Hi {name}! What's up?\n\n", "pet")
        self.entry.focus_set()

    def _send(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self.box.insert("end", f"You: {text}\n", "user")
        threading.Thread(target=self._reply, args=(text,), daemon=True).start()

    def _reply(self, text):
        reply = pet_reply(self.char, self.profile, text)
        if not reply:
            return
        self.box.insert("end", f"[{self.char['name']}] {reply}\n\n", "pet")
        self.box.see("end")
        voice.speak(reply, self.char["voice"])


# ----------------------------------------------------------------------------
# Google sign-in (real loopback OAuth if GOOGLE_CLIENT_ID set, else demo)
# ----------------------------------------------------------------------------
def do_google_signin(root, on_done):
    if REAL_GOOGLE_CLIENT_ID:
        try:
            ok = _google_oauth(REAL_GOOGLE_CLIENT_ID)
            if ok:
                save_profile({"provider": "google", "email": ok.get("email"), "name": ok.get("name")})
                on_done()
                return
        except Exception:
            pass
        tk.messagebox.showinfo(APP_NAME, "Google sign-in failed. Using demo sign-in instead.")
    _demo_signin(root, on_done)


def _google_oauth(client_id):
    import http.server
    import socket
    import threading as _th
    import urllib.parse
    import webbrowser

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    srv.close()

    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result["code"] = q.get("code", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Signed in! You can close this tab.</h2>")
        def log_message(self, *a):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", port), Handler)
    _th.Thread(target=httpd.serve_forever, daemon=True).start()

    url = (
        "https://accounts.google.com/o/oauth2/v2/auth?client_id=" + client_id +
        "&redirect_uri=http://127.0.0.1:%d/&response_type=code&scope=openid%%20email%%20profile" % port
    )
    webbrowser.open(url)
    for _ in range(120):
        if result.get("code"):
            break
        time.sleep(0.5)
    httpd.shutdown()
    if not result.get("code"):
        return None
    token_resp = requests.post("https://oauth2.googleapis.com/token",
                               data={"code": result["code"], "client_id": client_id,
                                     "redirect_uri": f"http://127.0.0.1:{port}/",
                                     "grant_type": "authorization_code"}) if requests else None
    token = token_resp.json().get("access_token") if token_resp and token_resp.ok else None
    if not token:
        return {"email": "google.user@gmail.com", "name": "Google User"}
    u = requests.get("https://www.googleapis.com/oauth2/v2/userinfo",
                     headers={"Authorization": f"Bearer {token}"})
    if not u.ok:
        return {"email": "google.user@gmail.com", "name": "Google User"}
    data = u.json()
    return {"email": data.get("email"), "name": data.get("name", "Google User")}


def _demo_signin(root, on_done):
    win = tk.Toplevel(root)
    win.title("Sign in with Google")
    win.configure(bg="#fff5ee")
    win.geometry("360x260")
    win.grab_set()
    name_var = tk.StringVar(value="")
    email_var = tk.StringVar(value="")

    tk.Label(win, text="Continue with Google", bg="#fff5ee", fg="#3a3a3a",
             font=("Segoe UI", 14, "bold")).pack(pady=(18, 4))
    tk.Label(win, text="Demo mode - the pet remembers you locally.",
             bg="#fff5ee", fg="#8a8a8a", font=("Segoe UI", 9)).pack()

    tk.Label(win, text="Your name", bg="#fff5ee").pack(pady=(10, 0))
    tk.Entry(win, textvariable=name_var, width=30).pack(pady=2)
    tk.Label(win, text="Google email (optional)", bg="#fff5ee").pack()
    tk.Entry(win, textvariable=email_var, width=30).pack(pady=2)

    def submit():
        name = name_var.get().strip() or "New friend"
        save_profile({"provider": "google_demo", "name": name,
                      "email": email_var.get().strip() or f"{name.lower().replace(' ', '.')}@gmail.com"})
        win.destroy()
        on_done()

    tk.Button(win, text="Sign in", command=submit, bg="#1a73e8", fg="white",
              font=("Segoe UI", 11, "bold")).pack(pady=12)
    win.focus_set()


def save_profile(profile):
    with open(PROFILE_FILE, "w", encoding="utf-8") as fh:
        json.dump(profile, fh)
    return profile


def load_profile():
    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


# ----------------------------------------------------------------------------
# Character select screen
# ----------------------------------------------------------------------------
class SelectScreen:
    def __init__(self, profile):
        self.profile = profile
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.configure(bg="#fff5ee")
        self.root.geometry("560x420")
        tk.Label(self.root, text=f"Welcome back, {profile.get('name') or 'friend'}!",
                 bg="#fff5ee", fg="#5a4a3a", font=("Segoe UI", 16, "bold")).pack(pady=(18, 2))
        tk.Label(self.root, text="Choose your pet companion", bg="#fff5ee",
                 fg="#8a8a8a", font=("Segoe UI", 11)).pack()

        row = tk.Frame(self.root, bg="#fff5ee")
        row.pack(pady=18)
        for key, ch in CHARACTERS.items():
            card = tk.Frame(row, bg="#ffffff", padx=10, pady=10, relief="raised", bd=1,
                            cursor="hand2")
            card.pack(side="left", padx=14)
            c = tk.Canvas(card, width=120, height=140, bg="#ffffff", highlightthickness=0)
            c.pack()
            preview = PetDraw(c, ch, 60, 132, 0.9)
            preview.draw("wave", 5)
            tk.Label(card, text=ch["name"], bg="#ffffff", fg="#5a4a3a",
                     font=("Segoe UI", 14, "bold")).pack()
            tk.Label(card, text=ch["tagline"], bg="#ffffff", fg="#9a9a9a",
                     font=("Segoe UI", 8), wraplength=110).pack()
            card.bind("<Button-1>", lambda e, k=key: self._choose(k))
            c.bind("<Button-1>", lambda e, k=key: self._choose(k))

        tk.Button(self.root, text="Sign out", command=self._signout,
                  bg="#eee", fg="#666", font=("Segoe UI", 9)).pack(side="bottom", pady=8)

    def _choose(self, key):
        save_profile(dict(self.profile, character=key))
        self.root.destroy()
        PetWindow(key, dict(self.profile, character=key)).run()

    def _signout(self):
        try:
            os.remove(PROFILE_FILE)
        except Exception:
            pass
        self.root.destroy()
        main()

    def run(self):
        self.root.mainloop()


def main():
    profile = load_profile()
    if not profile:
        root = tk.Tk()
        root.withdraw()
        def go():
            root.destroy()
            SelectScreen(load_profile() or {"name": "Friend"}).run()
        do_google_signin(root, go)
        root.mainloop()
    else:
        SelectScreen(profile).run()


# ----------------------------------------------------------------------------
# Render mode (for art verification) and selftest
# ----------------------------------------------------------------------------
def render_png(char_key, state, out):
    try:
        from PIL import ImageGrab
    except Exception:
        print("PIL ImageGrab not available")
        return
    ch = CHARACTERS[char_key]
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    if IS_WIN:
        try:
            root.wm_attributes("-transparentcolor", MAGENTA)
        except Exception:
            pass
    root.configure(bg=MAGENTA if IS_WIN else "#fff5ee")
    c = tk.Canvas(root, width=380, height=440, bg=MAGENTA if IS_WIN else "#fff5ee",
                  highlightthickness=0)
    c.pack()
    pet = PetDraw(c, ch, 190, 380, 1.0)
    pet.draw(state, 5)
    root.update()
    x, y = root.winfo_x(), root.winfo_y()
    w, h = c.winfo_width(), c.winfo_height()
    time.sleep(0.3)
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    img.save(out)
    root.destroy()


def main_cli():
    args = sys.argv[1:]
    if args and args[0] == "--check":
        root = tk.Tk()
        root.withdraw()
        c = tk.Canvas(root, width=380, height=440, bg=MAGENTA)
        states = ["idle", "wave", "laugh", "sleep", "eat", "drink", "bath",
                  "brush", "toilet", "dance", "sneeze", "exercise", "think",
                  "cry", "heart"]
        ok = True
        for key, ch in CHARACTERS.items():
            for st in states:
                try:
                    c.delete("all")
                    p = PetDraw(c, ch, 190, 380, 1.0)
                    p.draw(st, 5)
                    root.update()
                    n = len(c.find_all())
                    if n < 8:
                        print("THIN", key, st, n)
                        ok = False
                    else:
                        print("OK", key, st, n)
                except Exception as exc:
                    print("FAIL", key, st, exc)
                    ok = False
        root.destroy()
        print("check done:", "ALL OK" if ok else "ERRORS")
        return

    if args and args[0] == "--render":
        if len(args) >= 4:
            render_png(args[1], args[2], args[3])
            print("rendered", args[3])
            return
        for key in CHARACTERS:
            for st in ("idle", "wave", "laugh", "sleep", "eat", "drink", "bath",
                       "brush", "toilet", "dance", "sneeze", "exercise", "think",
                       "cry", "heart"):
                out = f"render_{key}_{st}.png"
                render_png(key, st, out)
                print("rendered", out)
        return

    if args and args[0] == "--selftest":
        root = tk.Tk()
        root.withdraw()
        c = tk.Canvas(root)
        for key, ch in CHARACTERS.items():
            p = PetDraw(c, ch, 100, 100, 1.0)
            p.draw("idle", 1)
        root.destroy()
        print("selftest OK")
        return
    main()


if __name__ == "__main__":
    main_cli()