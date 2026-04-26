"""
vision_service.py — Sends an image to Gemini Vision and returns adherence + pill JSON.

Standalone test:
    python vision_service.py test_capture_1.jpg
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

MODEL_NAME = "gemini-2.5-flash"

POSITION_TO_DAY = [
    "sunday", "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday",
]

PROMPT = """You are a medical adherence monitoring AI watching a senior take their daily medication through a head-mounted camera.

The image shows a 7-day pill organizer with compartments arranged in a single horizontal row.

CRITICAL — compartment layout (use POSITION from left, NOT the letter, to identify the day):
  Position 1 (leftmost):  S = SUNDAY
  Position 2:             M = MONDAY
  Position 3:             T = TUESDAY
  Position 4:             W = WEDNESDAY
  Position 5:             T = THURSDAY  (second T)
  Position 6:             F = FRIDAY
  Position 7 (rightmost): S = SATURDAY  (second S)

There are TWO "S" compartments (Sunday=position 1, Saturday=position 7) and TWO "T" compartments (Tuesday=3, Thursday=5). Always count from the left edge.

Return ONLY a valid JSON object with these exact fields:

{
  "pill_organizer_visible": boolean,
  "open_compartment_position": integer 1-7 or null,
  "open_compartment_day": derived from position above, or null,
  "open_compartment_state": "has_pills" | "empty" | null,
  "pills_in_compartment": [
    { "shape": "oval" | "round" | "capsule" | "square" | "other", "count": integer }
  ],
  "total_pills_visible": integer,
  "confidence": float 0.0-1.0,
  "scene_description": short string under 20 words
}

Pill shape definitions:
- "round"   = circular, disc-like (think aspirin)
- "oval"    = elongated, longer than wide, smooth ends (think ibuprofen tablet)
- "capsule" = two-tone cylindrical pill with rounded ends (think Tylenol gelcap)
- "square"  = squarish/rectangular tablet
- "other"   = anything that doesn't fit above

Rules:
- A compartment is "open" if its lid is visibly raised or removed.
- If multiple lids are open, pick the one MOST clearly raised.
- "pills_in_compartment" should list each distinct pill shape found inside the OPEN compartment, with how many of that shape are visible. Empty list [] if compartment is empty or none open.
- "total_pills_visible" = sum of all counts in pills_in_compartment.
- If the image is too dark, blurry, or no organizer visible, set pill_organizer_visible to false and other fields to null/empty.
- Return ONLY the JSON object. No markdown, no commentary.
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

    model = genai.GenerativeModel(MODEL_NAME)

    try:
        response = model.generate_content(
            [PROMPT, img],
            generation_config=GENERATION_CONFIG,
        )
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

    # Cross-check position vs day
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
