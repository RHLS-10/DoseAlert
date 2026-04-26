"""
voice_service.py — Speaks text in the cloned caregiver's voice via ElevenLabs.

Standalone test:
    python voice_service.py "Perfect Mom, that's your morning dose. Love you."
"""
import os
import sys
import tempfile
import pygame
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv()

API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = os.getenv("VOICE_ID")

if not API_KEY or not VOICE_ID:
    raise RuntimeError("Missing ELEVENLABS_API_KEY or VOICE_ID in .env")

client = ElevenLabs(api_key=API_KEY)

# Initialize pygame mixer once at import time
pygame.mixer.init()


def speak(text: str, mode: str = "confirm") -> None:
    """
    Generate speech from `text` in the cloned voice and play it through speakers.

    mode:
        "confirm" — warm, normal delivery (good dose taken)
        "alert"   — slightly more urgent (wrong compartment, missed dose)

    Blocks until playback finishes.
    """
    # Voice settings tweak per mode. ElevenLabs lets us shift stability/style.
    if mode == "alert":
        voice_settings = {
            "stability": 0.4,        # less stable = more emotional/urgent
            "similarity_boost": 0.85,
            "style": 0.5,
            "use_speaker_boost": True,
        }
    else:
        voice_settings = {
            "stability": 0.6,        # warmer, calmer
            "similarity_boost": 0.85,
            "style": 0.3,
            "use_speaker_boost": True,
        }

    print(f"[voice] ({mode}) speaking: {text!r}")

    # Stream audio bytes from ElevenLabs
    audio_stream = client.text_to_speech.convert(
        voice_id=VOICE_ID,
        text=text,
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
        voice_settings=voice_settings,
    )

    # Collect chunks into a single bytes object
    audio_bytes = b"".join(audio_stream)

    # Write to temp file (pygame.mixer.music loads files most reliably)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(audio_bytes)
        temp_path = f.name

    try:
        pygame.mixer.music.load(temp_path)
        pygame.mixer.music.play()
        # Block until audio finishes playing
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(20)
    finally:
        # Clean up temp file
        pygame.mixer.music.unload()
        try:
            os.remove(temp_path)
        except OSError:
            pass


# --- Standalone test ------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Default test phrases
        speak("Perfect Mom, that's your morning dose. Love you.", mode="confirm")
        speak("Wait Mom — that's tomorrow's pills, not today's.", mode="alert")
    else:
        text = " ".join(sys.argv[1:])
        speak(text)