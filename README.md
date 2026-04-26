# DoseAlert

**Watching over Mom, in your voice.**

> An AI-powered medication adherence system that uses computer vision to monitor seniors taking their daily medication — and gently confirms or alerts them in a loved one's cloned voice.

Built for **HackaBull VII** at the University of South Florida, April 25–26, 2026.

---

## The problem

**Medication non-adherence kills 125,000 Americans every year** and costs the U.S. healthcare system over $500 billion annually. For seniors with dementia, Alzheimer's, or simple memory decline, the questions are constant and unanswerable:

- *"Did I already take my pills today?"*
- *"Is this the right compartment?"*
- *"Are these the morning pills or the evening ones?"*

Existing solutions fall into two camps. Cheap pill reminders (smart caps, alarm clocks, paper charts) are easy to ignore and offer no verification. Clinical-grade systems ($500+ smart dispensers, in-home nursing) are expensive, intrusive, and feel like surveillance — exactly what aging-in-place seniors want to avoid.

**There's a missing middle**: something that watches *with* the senior, not over them, and intervenes only when needed — using the one voice they'll always listen to: a loved one's.

## The solution

DoseAlert is a wearable computer vision system that turns any pair of glasses into an attentive, gentle assistant. The senior wears a small IR camera mounted to a headband or glasses frame. Whenever they reach for their pill organizer, DoseAlert:

1. **Sees** the scene through the IR camera
2. **Understands** it using Google Gemini Vision — which compartment is open, what pills are inside, whether anything is missing
3. **Decides** in real time whether to confirm a correct dose or alert before a mistake happens
4. **Speaks** in the cloned voice of a daughter, son, spouse, or friend — turning a clinical AI into a familiar, trusted presence

Because the analysis happens *before* pills are swallowed, mistakes get caught — not just logged. And because the voice belongs to someone the senior loves, they listen.

---

## What judges will see in 60 seconds

```
1. The wearer puts on the IR-camera headset
2. They open today's compartment with both pills inside
   → "Perfect Mom, that's your oval and your round for Saturday. Love you."
3. They open a different day's compartment
   → "Wait Mom, that's Sunday's pills, not today's." (alert tone)
4. They open today's compartment EMPTY (already taken)
   → "You already took today's pills, Mom. Great job remembering."
5. The caregiver dashboard updates in real time —
   the family sees every dose confirmed, every alert raised,
   from anywhere
```

---

## How it works

```
┌───────────────────────────────┐
│  Glasses-mounted IR camera    │   Hardware: 4MP global-shutter IR cam
│  (4MP, USB)                   │   on a headband, plugged into a laptop
└───────────────┬───────────────┘
                │ frame every 4s
                ▼
┌───────────────────────────────┐
│  camera_driver.py             │   OpenCV capture, manual exposure control,
│                               │   live preview tuning (no auto-exposure
│                               │   on IR cams — has to be dialed in)
└───────────────┬───────────────┘
                │ JPEG
                ▼
┌───────────────────────────────┐
│  vision_service.py            │   Sends frame to Gemini 2.5 Flash with a
│  (Google Gemini Vision API)   │   structured prompt. Returns JSON:
│                               │     • which compartment is open (1-7)
│                               │     • which day that maps to
│                               │     • pills visible (shape + count)
│                               │     • confidence
└───────────────┬───────────────┘
                │ adherence JSON
                ▼
┌───────────────────────────────┐
│  main.py                      │   Compares Gemini's findings against:
│  (decision + state machine)   │     • today's actual day-of-week
│                               │     • the expected daily regimen
│                               │   Decides: confirm, alert, or stay silent.
│                               │   Debounces so it doesn't repeat itself.
└──┬────────────────────────┬───┘
   │ phrase                 │ event
   ▼                        ▼
┌───────────────┐   ┌────────────────┐
│ voice_        │   │ events.json    │
│ service.py    │   │                │  ◄── polled every 4s ──┐
│ ElevenLabs    │   │ append-only    │                        │
│ TTS, cloned   │   │ event log      │                        │
│ family voice  │   │                │                        │
└───────┬───────┘   └────────────────┘                ┌───────┴────────┐
        │                                             │ dashboard.html │
        ▼                                             │ (caregiver UI) │
   speakers                                           └────────────────┘
   (the moment that wins)
```

### Backend (Python)
The Python pipeline runs locally on the laptop the senior is already using. Five files, clear separation of concerns:

| File | Responsibility |
|---|---|
| `camera_driver.py` | OpenCV-based capture from the IR camera. Includes a live preview tool for tuning exposure and aiming the headmount. |
| `vision_service.py` | Wraps the Gemini API. Owns the prompt that turns a raw image into structured JSON about pill organizer state. |
| `voice_service.py` | Wraps the ElevenLabs TTS API. Plays cloned-voice audio through the laptop's speakers via pygame. |
| `main.py` | The orchestrator. Captures, analyzes, decides, speaks, logs. Contains the decision logic comparing what's seen against what's expected. |
| `events.json` | Append-only event log. The bridge between the Python loop and the web dashboard. |

### Frontend (Static Web Dashboard)
A single self-contained HTML file (`dashboard.html`) that the caregiver — daughter, spouse, adult son — opens in their browser to monitor a parent from anywhere. Three tabs:

- **Live activity** — auto-refreshes every 4 seconds. Shows every observation the system makes: confirmations in sage green, alerts in coral, missed doses flagged. Includes daily and weekly compliance stats.
- **Schedule** — visual calendar where the caregiver sets which days and times Mom takes her pills. Persists in localStorage.
- **Voice profile** — manage which loved one's voice DoseAlert speaks in. Upload a 30-second sample and ElevenLabs clones it. Multiple voice profiles can be saved (daughter, son, spouse) and switched at any time.

Built with vanilla HTML, Tailwind CSS (via CDN), and plain JavaScript. No build step. No framework. Loads in under 100ms.

---

## Tech stack

| Layer | Technology |
|---|---|
| Hardware | 4MP IR USB camera, head-mounted on glasses frame |
| Camera I/O | OpenCV (Python) with DirectShow backend on Windows |
| Vision AI | Google Gemini 2.5 Flash (multimodal) |
| Voice AI | ElevenLabs Instant Voice Cloning + Text-to-Speech |
| Audio playback | pygame |
| Frontend | Vanilla HTML + Tailwind CSS (CDN) + plain JS |
| Local data | `events.json` (append-only) + browser localStorage |
| Runtime | Python 3.11 on Windows (works on Mac/Linux) |

---

## Project structure

```
dosealert/
├── camera_driver.py      # IR camera capture + live preview tuner
├── vision_service.py     # Gemini Vision wrapper, structured prompt
├── voice_service.py      # ElevenLabs TTS + pygame playback
├── main.py               # Orchestrator: capture → analyze → decide → speak → log
├── dashboard.html        # Single-file caregiver web UI
├── events.json           # Live event log (the bridge between backend and frontend)
├── requirements.txt
├── .env.example          # Template for API keys & config
├── .env                  # Your actual keys (gitignored)
└── README.md             # This file
```

---

## Setup

### Prerequisites
- Python 3.11+
- A USB IR camera (or any USB webcam)
- A Google account for the Gemini API ([free tier works](https://aistudio.google.com/apikey))
- An ElevenLabs account ([free tier supports voice cloning](https://elevenlabs.io))
- ~30 seconds of clean audio of the loved one whose voice you want to clone

### Install

```bash
git clone <this-repo>
cd dosealert

python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
```

Edit `.env` and fill in:
```
GEMINI_API_KEY=your_key_from_aistudio
ELEVENLABS_API_KEY=your_key_from_elevenlabs
VOICE_ID=your_cloned_voice_id        # see below
CAMERA_INDEX=1                       # see below
EXPOSURE=-7                          # see below (IR cams only)
CAPTURE_INTERVAL=4
```

### Clone a voice in ElevenLabs

1. Record 30+ seconds of clear audio of the loved one (quiet room, normal speaking voice)
2. Go to [elevenlabs.io](https://elevenlabs.io) → Voice Lab → **Add Voice** → **Instant Voice Clone**
3. Upload the recording
4. Copy the resulting Voice ID into `VOICE_ID` in `.env`

### Find your camera index

```bash
python camera_driver.py --scan
```
This lists every camera attached to your laptop. Index 0 is usually the laptop webcam; the IR cam is typically 1 or 2. Set `CAMERA_INDEX` in `.env` accordingly.

### Tune the IR camera exposure

```bash
python camera_driver.py
```
A live preview opens. IR cameras don't auto-expose well in OpenCV, so:
- Press `-` / `+` to dial exposure darker / brighter until the pill organizer is clearly visible
- Press `A` to try Windows-style auto-exposure
- Press `C` to capture a test frame
- Press `Q` to quit — the terminal will tell you the final exposure value to put in `.env`

---

## Run

```bash
python main.py
```

You'll see live status in the terminal:
```
============================================================
  DoseAlert — watching for medication adherence
  Today: SATURDAY  (Saturday, April 25)
  Expected regimen: {'oval': 1, 'round': 1}
  Capture interval: 4.0s
============================================================

[20:32:14] Frame #1
  → day=None  state=None  pills=[]  conf=0.95
[20:32:18] Frame #2
  → day=saturday  state=has_pills  pills=[{'shape': 'oval', 'count': 1}, {'shape': 'round', 'count': 1}]
  🔊 [CONFIRMED] Perfect Mom, that's your oval and your round for Saturday. Love you.
```

In a separate terminal, start the dashboard:
```bash
python -m http.server 8000
```
Open [http://localhost:8000/dashboard.html](http://localhost:8000/dashboard.html) in any browser.

---

## Configuration & customization

The expected daily medication regimen lives at the top of `main.py`:
```python
EXPECTED_REGIMEN = {"oval": 1, "round": 1}
```
Change this to match what Mom actually takes (e.g. `{"capsule": 2, "round": 1}`).

Pill-organizer layout (compartment-to-day mapping) lives at the top of `vision_service.py`:
```python
POSITION_TO_DAY = ["sunday", "monday", "tuesday", ..., "saturday"]
```
Adjust if the user's organizer is laid out Monday-first or includes AM/PM compartments.

---

## Hackathon tracks

DoseAlert was built to compete in:

- **Tech for Good** — accessibility for seniors and people with cognitive decline
- **Healthcare & Wellness** — verifiable medication adherence
- **Hardware** — IR camera + headmount + edge processing on a laptop
- **Best Use of Gemini API** — multimodal vision for real-world health monitoring
- **Best Use of ElevenLabs** — cloned voice as a trust mechanism, not just narration

---

## Privacy & safety

- All voice cloning is opt-in and stays under the family's control. Voice IDs live in the user's ElevenLabs account.
- Camera frames are never stored long-term. Only the most recent frame is kept on disk (`current_frame.jpg`) and overwritten on the next capture.
- The event log (`events.json`) lives entirely on the local laptop. No medication data leaves the device unless the family chooses to forward it.
- DoseAlert is a **monitoring and alerting tool**, not a medical device. It supplements caregivers and clinicians; it does not replace them.

---

## What we'd build next

- **Mobile companion app** so the family can see Mom's adherence from their phone, get push notifications for missed doses
- **Video summary** — short auto-clipped recording of each medication event the caregiver can review
- **Multi-medication scheduling** — different regimens for AM vs PM, weekday vs weekend
- **Clinical integrations** — push adherence data to EHRs and pharmacy refill systems
- **Dedicated wearable hardware** — drop the laptop dependency, run inference on-device with a small ESP32-class board

---

## License

MIT. Built with love at HackaBull VII.

## Acknowledgements

Thanks to Google AI Studio (Gemini), ElevenLabs (voice cloning), and the HackaBull VII organizers at USF for the venue, the snacks, and the chance to build.
