"""
vision_service.py — Multi-reference few-shot vision.

Loads two reference photos of the user's actual pill organizer (top-down + angled)
and sends them to Gemini alongside each live frame. Gemini compares the live frame
to the references and only triggers when it sees that specific object.

Reference files expected in the dosealert folder:
    reference_pillbox_top.jpg     (top-down view, all compartments visible)
    reference_pillbox_angle.jpg   (30-45 degree angle, matches head-cam perspective)

Capture them with:
    python camera_driver.py --capture reference_pillbox_top.jpg
    python camera_driver.py --capture reference_pillbox_angle.jpg
"""
import os
import sys
import json
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY in .env")

genai.configure(api_key=API_KEY)

MODEL_NAME = "gemini-2.5-flash-lite"
MAX_DIM = 640

REFERENCE_PATHS = [
    "reference_pillbox_top.jpg",
    "reference_pillbox_angle.jpg",
]

POSITION_TO_DAY = [
    "sunday", "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday",
]


def _load_reference(path):
    if not os.path.exists(path):
        return None
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((MAX_DIM, MAX_DIM))
    return img


_references = [(p, _load_reference(p)) for p in REFERENCE_PATHS]
_loaded_refs = [img for _, img in _references if img is not None]

if _loaded_refs:
    for path, img in _references:
        status = "✓" if img is not None else "✗ (missing)"
        print(f"[vision] {status} {path}")
    print(f"[vision] using {len(_loaded_refs)} reference image(s) for few-shot detection")
else:
    print("[vision] ⚠️  no reference images found")
    print("[vision]    capture with:")
    for p in REFERENCE_PATHS:
        print(f"[vision]      python camera_driver.py --capture {p}")
    print("[vision]    falling back to generic detection (less accurate)")


PROMPT_WITH_REFERENCES = """You are a medical adherence monitoring AI watching a senior take their daily medication.

You receive multiple images:
  IMAGE 1, IMAGE 2 (and possibly more) — REFERENCE PHOTOS of the EXACT pill organizer the user owns, from different angles.
  FINAL IMAGE — LIVE frame from the head-mounted camera.

CRITICAL: Only set pill_organizer_visible=true if the FINAL image contains the SAME pill organizer shown in the reference photos. Other objects (earbuds cases, electronics, books, food containers, jewelry boxes) are NOT pill organizers — return false even if they superficially resemble one. Compare carefully.

The pill organizer has 7 compartments arranged in a horizontal row. Position-to-day mapping:
  Position 1 (leftmost):  S = SUNDAY
  Position 2:             M = MONDAY
  Position 3:             T = TUESDAY
  Position 4:             W = WEDNESDAY
  Position 5:             T = THURSDAY  (second T)
  Position 6:             F = FRIDAY
  Position 7 (rightmost): S = SATURDAY  (second S)

Return ONLY a valid JSON object:
{
  "pill_organizer_visible": boolean,
  "open_compartment_position": integer 1-7 or null,
  "open_compartment_day": derived from position above, or null,
  "open_compartment_state": "has_pills" | "empty" | null,
  "pills_in_compartment": [{"shape": "oval"|"round"|"capsule"|"square"|"other", "count": integer}],
  "total_pills_visible": integer,
  "confidence": float 0.0-1.0,
  "scene_description": short string under 20 words
}

Pill shapes: round (circular), oval (elongated), capsule (two-tone cylindrical), square, other.
Be CONSERVATIVE — when unsure, return pill_organizer_visible=false. False positives are worse than false negatives.
Return ONLY the JSON object. No markdown, no commentary.
"""

PROMPT_NO_REFERENCE = """You are a medical adherence monitoring AI watching a senior take their daily medication.

The image may show a 7-day pill organizer with compartments arranged in a horizontal row. Position-to-day:
  1 (leftmost) S=SUNDAY, 2 M=MONDAY, 3 T=TUESDAY, 4 W=WEDNESDAY,
  5 T=THURSDAY, 6 F=FRIDAY, 7 (rightmost) S=SATURDAY.

Return ONLY a valid JSON object:
{
  "pill_organizer_visible": boolean,
  "open_compartment_position": integer 1-7 or null,
  "open_compartment_day": derived from position, or null,
  "open_compartment_state": "has_pills" | "empty" | null,
  "pills_in_compartment": [{"shape": "oval"|"round"|"capsule"|"square"|"other", "count": integer}],
  "total_pills_visible": integer,
  "confidence": float 0.0-1.0,
  "scene_description": short string under 20 words
}

Be CONSERVATIVE — earbuds cases, electronics, food containers and jewelry boxes are NOT pill organizers.
Return ONLY the JSON object.
"""

GENERATION_CONFIG = {
    "response_mime_type": "application/json",
    "temperature": 0.1,
}


def analyze_frame(image_path: str) -> dict:
    try:
        img = Image.open(image_path)
    except Exception as e:
        return {"error": f"could not open image: {e}"}

    if img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((MAX_DIM, MAX_DIM))

    model = genai.GenerativeModel(MODEL_NAME)

    if _loaded_refs:
        content = [PROMPT_WITH_REFERENCES, *_loaded_refs, img]
    else:
        content = [PROMPT_NO_REFERENCE, img]

    try:
        response = model.generate_content(content, generation_config=GENERATION_CONFIG)
    except Exception as e:
        return {"error": f"Gemini API error: {e}"}

    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"error": f"could not parse JSON: {e}", "raw": raw}

    pos = result.get("open_compartment_position")
    if isinstance(pos, int) and 1 <= pos <= 7:
        derived_day = POSITION_TO_DAY[pos - 1]
        if result.get("open_compartment_day") != derived_day:
            result["open_compartment_day_raw"] = result.get("open_compartment_day")
            result["open_compartment_day"] = derived_day
            result["_corrected"] = True

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python vision_service.py <image_path>")
        sys.exit(1)
    print(f"Analyzing {sys.argv[1]}...\n")
    print(json.dumps(analyze_frame(sys.argv[1]), indent=2))
