"""
main.py — DoseAlert main loop.

Captures frames, analyzes via Gemini, decides what to say based on what
pills are visible vs what's expected for today, speaks in the cloned voice,
and logs to events.json.
"""
import os
import time
import json
import traceback
from datetime import datetime
from dotenv import load_dotenv

from camera_driver import Camera
from vision_service import analyze_frame
from voice_service import speak

load_dotenv()

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def get_today() -> str:
    override = os.getenv("TODAY_OVERRIDE", "").strip().lower()
    if override in DAYS:
        return override
    return DAYS[datetime.now().weekday()]


TODAY = get_today()
CAPTURE_INTERVAL = float(os.getenv("CAPTURE_INTERVAL", "4"))
FRAME_PATH = "current_frame.jpg"
EVENTS_FILE = "events.json"

# Mom's daily regimen — expected pills for each day.
# {shape: count}. Same regimen every day in this demo.
EXPECTED_REGIMEN = {"oval": 1, "round": 1}
EXPECTED_TOTAL = sum(EXPECTED_REGIMEN.values())


# --- Phrase generators ---------------------------------------------------
def shapes_phrase(regimen: dict) -> str:
    """Convert {oval: 1, round: 1} -> 'your oval and your round'"""
    parts = []
    for shape, count in regimen.items():
        if count == 1:
            parts.append(f"your {shape}")
        else:
            parts.append(f"your {count} {shape}s")
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def confirm_phrase(found_pills: dict) -> str:
    return f"Perfect Mom, that's {shapes_phrase(found_pills)} for {TODAY.capitalize()}. Love you."


def alert_wrong_day(wrong_day: str) -> str:
    return f"Wait Mom, that's {wrong_day.capitalize()}'s pills, not today's."


def alert_missing_pill(missing: dict) -> str:
    return f"Mom, I don't see {shapes_phrase(missing)} in there. Are you sure that's all of today's pills?"


def alert_extra_pill() -> str:
    return f"Mom, that looks like more pills than you should be taking today."


def already_taken_phrase() -> str:
    return f"You already took today's pills, Mom. Great job remembering."


# --- Event logging --------------------------------------------------------
def load_events():
    try:
        with open(EVENTS_FILE) as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def log_event(status, compartment, message, confidence, pills=None):
    events = load_events()
    events.insert(0, {
        "time": datetime.now().isoformat(),
        "status": status,
        "compartment": compartment,
        "message": message,
        "confidence": confidence,
        "pills": pills,
        "today": TODAY,
    })
    events = events[:100]
    with open(EVENTS_FILE, "w") as f:
        json.dump(events, f, indent=2)


# --- Decision logic -------------------------------------------------------
def pills_to_dict(pills_list) -> dict:
    """Convert [{'shape': 'oval', 'count': 1}, ...] -> {'oval': 1, ...}"""
    if not pills_list:
        return {}
    return {p["shape"]: p["count"] for p in pills_list if "shape" in p and "count" in p}


def decide(vision_result: dict):
    """Returns (status, phrase, pills_dict) or (None, None, None) for no action."""
    if not vision_result.get("pill_organizer_visible"):
        return None, None, None

    day = vision_result.get("open_compartment_day")
    state = vision_result.get("open_compartment_state")
    found = pills_to_dict(vision_result.get("pills_in_compartment", []))

    if day is None:
        return None, None, None

    # Wrong day
    if day != TODAY and state == "has_pills":
        return "alert", alert_wrong_day(day), found

    # Right day, empty
    if day == TODAY and state == "empty":
        return "info", already_taken_phrase(), {}

    # Right day, has pills — check the regimen matches
    if day == TODAY and state == "has_pills":
        # Missing any expected pills?
        missing = {
            shape: EXPECTED_REGIMEN[shape] - found.get(shape, 0)
            for shape in EXPECTED_REGIMEN
            if found.get(shape, 0) < EXPECTED_REGIMEN[shape]
        }
        if missing:
            return "alert", alert_missing_pill(missing), found

        # Extra unexpected pills?
        extra_shapes = [s for s in found if s not in EXPECTED_REGIMEN]
        if extra_shapes or sum(found.values()) > EXPECTED_TOTAL:
            return "alert", alert_extra_pill(), found

        # All expected pills present — confirm
        return "confirmed", confirm_phrase(found), found

    return None, None, None


# --- Main loop -----------------------------------------------------------
def main():
    print("=" * 60)
    print("  DoseAlert — watching for medication adherence")
    print(f"  Today: {TODAY.upper()}  ({datetime.now().strftime('%A, %B %d')})")
    print(f"  Expected regimen: {EXPECTED_REGIMEN}")
    print(f"  Capture interval: {CAPTURE_INTERVAL}s")
    print(f"  Press Ctrl+C to stop")
    print("=" * 60)

    cam = Camera()
    last_state = (None, None, None)  # (day, state, pills_signature)
    iteration = 0

    try:
        while True:
            iteration += 1
            t0 = time.time()
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Frame #{iteration}")

            frame = cam.capture_frame(FRAME_PATH)
            if frame is None:
                print("  ⚠️  capture failed, retrying in 2s")
                time.sleep(2)
                continue

            try:
                result = analyze_frame(FRAME_PATH)
            except Exception as e:
                print(f"  ⚠️  vision error: {e}")
                time.sleep(CAPTURE_INTERVAL)
                continue

            if "error" in result:
                print(f"  ⚠️  {result['error']}")
                time.sleep(CAPTURE_INTERVAL)
                continue

            day = result.get("open_compartment_day")
            state = result.get("open_compartment_state")
            pills = result.get("pills_in_compartment", [])
            conf = result.get("confidence")
            print(f"  → day={day}  state={state}  pills={pills}  conf={conf}")

            status, phrase, pills_dict = decide(result)
            pills_sig = json.dumps(pills_dict, sort_keys=True) if pills_dict else None
            current_state = (day, state, pills_sig)

            if phrase and current_state != last_state:
                print(f"  🔊 [{status.upper()}] {phrase}")
                log_event(status, day, phrase, conf, pills_dict)
                try:
                    mode = "alert" if status == "alert" else "confirm"
                    speak(phrase, mode=mode)
                except Exception as e:
                    print(f"  ⚠️  voice error: {e}")
            elif phrase is None and day is not None:
                print(f"  ⏸  no action")

            last_state = current_state

            elapsed = time.time() - t0
            time.sleep(max(0, CAPTURE_INTERVAL - elapsed))

    except KeyboardInterrupt:
        print("\n\nStopped.")
    except Exception as e:
        print(f"\n\nFatal: {e}")
        traceback.print_exc()
    finally:
        cam.release()


if __name__ == "__main__":
    main()
