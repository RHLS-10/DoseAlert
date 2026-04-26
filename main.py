"""
main.py — DoseAlert v2 (full happy path).

Flow within one dose:
  1. Speak prompt: "Hey, time for your pills"
  2. Wait for pill box in frame   → "Great job, I can see your pill box."
  3. Coach to open today          → "Now open today's compartment — Sunday."
  4. Watch for compartment open:
       a. today + has_pills        → "Perfect, take those with water."
       b. wrong day + has_pills    → "Wait, that's Tuesday. Try the Sunday one."
                                     (one-shot — won't repeat for same day)
       c. nothing for 20s          → nudge once: "Mom, open the Sunday compartment."
  5. Watch for pills to disappear (today: has_pills → empty)
       → "Great job, you took your pills. Love you. Talk to you later."
  6. Total session timeout 120s → "No meds today."

Run:    python main.py
Quit:   Ctrl+C  (or Q in preview window)
"""
import os
import time
import json
import queue
import threading
import cv2
from datetime import datetime
from dotenv import load_dotenv

from camera_driver import Camera
from vision_service import analyze_frame
from voice_service import speak

load_dotenv()

DEMO_DELAY_SECONDS = 30
SESSION_TIMEOUT_SECONDS = 120
ANALYSIS_INTERVAL = 0.5
NUDGE_AFTER_SECONDS = 20
FRAME_PATH = "current_frame.jpg"
EVENTS_FILE = "events.json"

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
TODAY = os.getenv("TODAY_OVERRIDE", "").strip().lower() or DAYS[datetime.now().weekday()]


# --- Speech queue (sequential, non-blocking) ----------------------------
_speech_q = queue.Queue()


def _speech_worker():
    while True:
        text, mode = _speech_q.get()
        try:
            speak(text, mode=mode)
        except Exception as e:
            print(f"  ⚠️  voice: {e}")


threading.Thread(target=_speech_worker, daemon=True).start()


def say(text: str, mode: str = "confirm"):
    print(f"  🔊 {text}")
    _speech_q.put((text, mode))


# --- Event logging ------------------------------------------------------
def log_event(status: str, message: str, **extra):
    try:
        with open(EVENTS_FILE) as f:
            events = json.load(f)
            if not isinstance(events, list):
                events = []
    except (FileNotFoundError, json.JSONDecodeError):
        events = []
    event = {
        "time": datetime.now().isoformat(),
        "status": status,
        "message": message,
    }
    event.update(extra)
    events.insert(0, event)
    with open(EVENTS_FILE, "w") as f:
        json.dump(events[:100], f, indent=2)


# --- Background vision (so the live feed never freezes) -----------------
vision = {"analyzing": False, "result_seq": 0, "result": None, "last_call": 0.0}
vision_lock = threading.Lock()


def vision_worker(frame_path):
    try:
        result = analyze_frame(frame_path)
        with vision_lock:
            vision["result"] = result
            vision["result_seq"] += 1
    finally:
        with vision_lock:
            vision["analyzing"] = False


def reset_vision_state():
    with vision_lock:
        vision["analyzing"] = False
        vision["result"] = None
        vision["result_seq"] = 0
        vision["last_call"] = 0.0


# --- Main session -------------------------------------------------------
def run_session() -> str:
    """
    Returns:
        'success'   — pills taken
        'no_box'    — never saw box
        'no_action' — saw box but pills not taken in time
    """
    cam = Camera()
    start = time.time()
    reset_vision_state()
    last_consumed = 0

    box_seen = False
    coached_to_open = False
    coaching_started_at = None
    nudged = False
    last_state_with_day = None      # (day, state) — last non-null observation
    last_correction_for = None      # day we last corrected user about

    try:
        while time.time() - start < SESSION_TIMEOUT_SECONDS:
            frame = cam.capture_frame()
            if frame is None:
                time.sleep(0.05)
                continue

            # Live preview
            elapsed = int(time.time() - start)
            remaining = SESSION_TIMEOUT_SECONDS - elapsed
            display = frame.copy()
            with vision_lock:
                analyzing = vision["analyzing"]
            label = "Analyzing..." if analyzing else f"Watching... {remaining}s left"
            cv2.putText(display, label, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.imshow("DoseAlert", display)

            # Trigger vision in background
            with vision_lock:
                last_call = vision["last_call"]
                busy = vision["analyzing"]
            if not busy and time.time() - last_call > ANALYSIS_INTERVAL:
                cv2.imwrite(FRAME_PATH, frame)
                with vision_lock:
                    vision["analyzing"] = True
                    vision["last_call"] = time.time()
                threading.Thread(target=vision_worker, args=(FRAME_PATH,), daemon=True).start()

            # Get fresh result
            with vision_lock:
                if vision["result_seq"] > last_consumed:
                    last_consumed = vision["result_seq"]
                    result = vision["result"]
                else:
                    result = None

            if result and "error" not in result:
                box_visible = bool(result.get("pill_organizer_visible"))
                day = result.get("open_compartment_day")
                state = result.get("open_compartment_state")

                # ─── Phase 1: looking for box ───
                if not box_seen:
                    if box_visible:
                        box_seen = True
                        say("Great job, I can see your pill box.")
                        log_event("info", "Pill box detected")

                # ─── Phase 2: coach to open today's compartment ───
                elif not coached_to_open:
                    say(f"Now open today's compartment — {TODAY.capitalize()}.")
                    log_event("info", f"Coached user to open {TODAY}")
                    coached_to_open = True
                    coaching_started_at = time.time()

                # ─── Phase 3: watching their actions ───
                else:
                    # Only act on observations where a compartment is identified
                    if day is not None:
                        # Did pills just disappear from today's compartment? → SUCCESS
                        if (last_state_with_day == (TODAY, "has_pills")
                                and (day, state) == (TODAY, "empty")):
                            say("Great job, you took your pills. Love you. Talk to you later.")
                            log_event("confirmed", "Pills taken successfully",
                                      compartment=TODAY)
                            return "success"

                        # New compartment-open transition?
                        if (day, state) != last_state_with_day:
                            if day == TODAY and state == "has_pills":
                                say("Perfect, take those pills with some water.")
                                log_event("info", "Correct compartment opened",
                                          compartment=TODAY)
                            elif day != TODAY and state == "has_pills":
                                if last_correction_for != day:
                                    say(f"Wait, that's {day.capitalize()}. Try the {TODAY.capitalize()} one instead.",
                                        mode="alert")
                                    log_event("alert", f"Wrong compartment ({day}) opened",
                                              compartment=day)
                                    last_correction_for = day
                            elif day == TODAY and state == "empty":
                                # opened today's already-empty compartment
                                say("Looks like you already took those, Mom. Good for you.")
                                log_event("info", "Today's compartment already empty",
                                          compartment=TODAY)
                                return "success"

                        last_state_with_day = (day, state)

                    # Nudge if no compartment opened after grace
                    if (not nudged and day is None and coaching_started_at
                            and time.time() - coaching_started_at > NUDGE_AFTER_SECONDS):
                        say(f"Mom, go ahead and open the {TODAY.capitalize()} compartment.")
                        log_event("info", "Nudged user")
                        nudged = True

            if cv2.waitKey(1) & 0xFF == ord("q"):
                return "no_action"

        # Timed out
        return "no_box" if not box_seen else "no_action"

    finally:
        cam.release()
        cv2.destroyAllWindows()


def run_dose():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Dose time  (today: {TODAY})")
    say("Hey, it's time for your pills.")
    log_event("info", "Dose started — prompting user")

    outcome = run_session()

    if outcome == "success":
        # Success message already spoken inside the session
        print("✅ Success")
    elif outcome == "no_box":
        say("No meds today.", mode="alert")
        log_event("alert", "No pill box detected within session window")
        print("❌ No box")
    else:
        say("No meds today.", mode="alert")
        log_event("alert", "Pill box detected but pills were not taken")
        print("❌ No action")

    # Wait for last speech to finish before returning to idle
    _speech_q.join() if False else time.sleep(0.5)  # keep simple; queue drains in bg


def main():
    print("=" * 60)
    print(f"  DoseAlert v2 — today is {TODAY.upper()}")
    print(f"  First dose in {DEMO_DELAY_SECONDS}s — Ctrl+C to quit")
    print("=" * 60)

    next_dose_at = time.time() + DEMO_DELAY_SECONDS

    while True:
        if time.time() >= next_dose_at:
            run_dose()
            next_dose_at = time.time() + DEMO_DELAY_SECONDS
            print(f"\n⏳ Next dose in {DEMO_DELAY_SECONDS}s...")
        else:
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
