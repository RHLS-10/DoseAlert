"""
camera_driver.py — IR camera (or webcam) capture via OpenCV.

Standalone uses:
    python camera_driver.py --scan        # find which index your IR camera is on
    python camera_driver.py               # live preview, press C to capture, Q to quit
    python camera_driver.py --capture out.jpg   # one-shot capture to file
"""
import os
import sys
import time
import cv2
from dotenv import load_dotenv

load_dotenv()

DEFAULT_INDEX = int(os.getenv("CAMERA_INDEX", "1"))


class Camera:
    """Wrapper around cv2.VideoCapture. Use as context manager or call .release()."""

    def __init__(self, index: int = DEFAULT_INDEX, use_dshow: bool = True):
        self.index = index
        # CAP_DSHOW is much more reliable on Windows for USB cams.
        # On Mac/Linux it's ignored or harmless.
        backend = cv2.CAP_DSHOW if use_dshow and sys.platform == "win32" else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(index, backend)

        if not self.cap.isOpened():
            raise RuntimeError(
                f"Could not open camera at index {index}. "
                f"Run `python camera_driver.py --scan` to find the right index."
            )

        # Give the camera a moment to warm up — first frame is often black
        time.sleep(0.5)
        # Discard a few frames to let auto-exposure settle
        for _ in range(3):
            self.cap.read()

    def capture_frame(self, save_path: str | None = None):
        """
        Capture a single frame. Returns the frame (numpy array) or None on failure.
        If save_path is given, writes JPEG to that path.
        """
        ret, frame = self.cap.read()
        if not ret or frame is None:
            print(f"[camera] WARNING: failed to read frame from index {self.index}")
            return None

        if save_path:
            cv2.imwrite(save_path, frame)
            print(f"[camera] saved {save_path} ({frame.shape[1]}x{frame.shape[0]})")

        return frame

    def release(self):
        if self.cap.isOpened():
            self.cap.release()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.release()


def scan_cameras(max_index: int = 5):
    """Try opening cameras at indices 0..max_index and report which work."""
    print("Scanning camera indices...\n")
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    found = []
    for i in range(max_index + 1):
        cap = cv2.VideoCapture(i, backend)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                h, w = frame.shape[:2]
                channels = frame.shape[2] if len(frame.shape) > 2 else 1
                kind = "grayscale/IR" if channels == 1 else f"{channels}-channel"
                print(f"  Index {i}: WORKING — {w}x{h}, {kind}")
                found.append(i)
            else:
                print(f"  Index {i}: opens but won't read frames")
            cap.release()
        else:
            print(f"  Index {i}: not available")
    print()
    if found:
        print(f"Use one of these indices in .env → CAMERA_INDEX={found[0]}")
        if len(found) > 1:
            print(f"  (laptop webcam is usually index 0; IR cam is one of {found[1:]})")
    else:
        print("No cameras found. Check USB connection and drivers.")
    return found


def preview_loop(index: int = DEFAULT_INDEX):
    """Open a live preview window. C = capture, Q = quit."""
    print(f"Opening preview on camera index {index}")
    print("  Press C to capture a test frame")
    print("  Press Q to quit")

    with Camera(index) as cam:
        shot_num = 0
        while True:
            frame = cam.capture_frame()
            if frame is None:
                print("[preview] no frame, retrying...")
                time.sleep(0.1)
                continue

            cv2.imshow("DoseAlert camera preview (C=capture, Q=quit)", frame)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break
            elif key == ord("c"):
                shot_num += 1
                path = f"test_capture_{shot_num}.jpg"
                cv2.imwrite(path, frame)
                print(f"[preview] saved {path}")

    cv2.destroyAllWindows()


# --- CLI ----------------------------------------------------------------
if __name__ == "__main__":
    args = sys.argv[1:]

    if "--scan" in args:
        scan_cameras()
    elif "--capture" in args:
        idx = args.index("--capture")
        out = args[idx + 1] if idx + 1 < len(args) else "capture.jpg"
        with Camera() as cam:
            cam.capture_frame(out)
    else:
        preview_loop()
