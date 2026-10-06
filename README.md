# Ping & Purr

An animated desktop friend who lives on your screen, talks to you, and does all the silly human things: bubble baths, brushing teeth, dancing, laughing, exercising, sleeping, and real AI chat.

## Download

Latest release assets (see [Releases](../../releases)):

| File | What it is |
|---|---|
| **PingPurr.exe** | Windows standalone app — no Python, no install, double-click and go |
| PingPurr_Windows.zip | Windows source package (`.bat` launcher, needs Python 3.10+) |
| PingPurr_Mac.zip | macOS source package (`run_mac.command`, needs Python 3.10+) |
| pingpurr.ico | App icon |

## About "Windows protected your PC" / Smart App Control

Ping & Purr is a small, independent, **unsigned** app. Everything runs 100% on your machine — nothing is uploaded, nothing is tracked. Windows and browsers flag unknown unsigned downloads by design:

- **"Keep anyway" / "Run anyway"** — one click in the browser download or SmartScreen prompt. Safe to allow.
- **Smart App Control (Windows 11)** — stricter; has no "run anyway". Turn it off under *Windows Security → App & browser control → Smart App Control*. It cannot be re-enabled without resetting Windows.
- The only way to remove these prompts is a paid code-signing certificate, which indie projects typically only adopt once funded.

## Quick start

1. **Windows**: download `PingPurr.exe` and double-click it.
2. **macOS / source**: install **Python 3.10+**, unzip `PingPurr_Mac.zip`, double-click `run_mac.command` (right-click → Open the first time).
3. Sign in with Google (demo sign-in also works) → choose **Zara** or **Max**.

## Features

- Two characters — **Zara** and **Max** — each with their own voice and personality
- 15 procedurally animated behaviors: baths, grooming, dancing, napping, and more
- Needs engine: hunger, energy, and affection, tracked live
- Conversational AI (offline scripted fallback included)
- Runs entirely offline and locally by default
- Always-on-top, draggable companion window

## Controls

| Interaction | What happens |
|---|---|
| Left-click | Hug + happy hearts |
| Drag | Move anywhere on screen |
| Right-click | Menu: Eat, Drink, Bath, Brush teeth, Sleep, Dance, Exercise, Laugh, Sneeze, Chat, **Listen**, Mute, Quit |

### Talk to your pet

Right-click the pet → **Listen / Stop listening**. The pet hears your microphone
and replies out loud:

- Online, it uses Google Web Speech (the app's only network call for voice; conversation
  via Groq is separate and optional).
- If the `LLM_API_KEY` env var is set (or the Groq key fails), replies are fully local.
- To run offline with a local model: download a **vosk small en-us model**, point the
  `PINGPURR_VOSK_MODEL` env var at its folder, and it never touches the network.
- Reply speed depends on your mic and internet. Low volume/background noise can cause
  silence; say "hello" clearly.

## Development

```bash
pip install pyaudio   # needed for voice listening (pip install pyaudiowpatch on Windows)
python pet_app.py
```

## License

MIT