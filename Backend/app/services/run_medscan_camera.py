"""
MedScan analyzer for medication detection on camera.
Usage:
  1. Run live camera detection with default references:
     python Backend/app/services/run_medscan_camera.py
  
  2. Run live camera detection using a patient's medication references:
     python Backend/app/services/run_medscan_camera.py --patient <patient_id>
  
  3. Batch process all medication photos for a specific patient:
     python Backend/app/services/run_medscan_camera.py --batch --patient <patient_id>

Notes:
- Press 'q' to quit the camera.
- Ensure OpenCV is installed (`pip install opencv-python`) and EasyOCR (`pip install easyocr`).
- If reference images are not available, ORB matching will simply not find matches.
- Photos are expected in: data/medications/{patient_id}/*/*.jpg
"""

import sys
import asyncio
import argparse
import tempfile
import time
from pathlib import Path

# Add Backend to path so imports work when run from project root
backend_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_path))

import cv2

from app.database import connect_to_mongo, close_mongo_connection, get_db
from app.services.medscan_service import MedScanAnalyzer, get_medscan_analyzer

SCREEN_WINDOW = "MedScan Detection"


def _normalize_medicine_key(value: str | None) -> str:
    import re
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").strip())
    cleaned = cleaned.strip("_")
    return cleaned.lower() or "unknown"


async def _load_patient_reference_images_from_db(patient_id: str) -> list[tuple[str, str]]:
    await connect_to_mongo()
    try:
        db = get_db()
        if db is None:
            return []

        reference_images: list[tuple[str, str]] = []
        cursor = db.medications.find({"patient_id": str(patient_id)}).sort("created_at", -1)
        async for medication in cursor:
            key = _normalize_medicine_key(medication.get("name") or medication.get("medication_name"))
            paths = []
            photo_urls = medication.get("photo_urls") or []
            if isinstance(photo_urls, list):
                paths.extend(photo_urls)
            photo_url = medication.get("photo_url")
            if photo_url:
                paths.append(photo_url)

            for raw_path in paths:
                path = Path(raw_path)
                if path.exists():
                    reference_images.append((key, str(path)))

        return reference_images
    finally:
        await close_mongo_connection()


def draw_detection_overlay(frame, result: dict):
    """Draw detection bbox and labels on frame in-place."""
    primary = result.get("primary_detection")
    if primary and primary.get("bbox"):
        x, y, w, h = primary["bbox"] if isinstance(primary["bbox"], (list, tuple)) else primary["bbox"]
        # ensure ints
        x, y, w, h = int(x), int(y), int(w), int(h)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (16, 204, 60), 2)
        label = f"{primary.get('name', primary.get('medicine_key', 'Unknown'))} {int(primary.get('confidence',0)*100)}%"
        cv2.putText(frame, label, (x, max(10, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    # show OCR text if present
    ocr = result.get("ocr_text")
    if ocr:
        y0 = 20
        for i, line in enumerate((ocr or "").split("\n")[:3]):
            cv2.putText(frame, line, (10, y0 + i * 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)


def process_patient_medications(patient_id: str):
    """Process all medication images for a specific patient."""
    med_dir = Path("data") / "medications" / patient_id
    if not med_dir.exists():
        print(f"ERROR: No medications folder found for patient {patient_id} at {med_dir}")
        return

    print(f"Loading medication references from database for patient {patient_id}...")
    reference_images = asyncio.run(_load_patient_reference_images_from_db(patient_id))
    if not reference_images:
        print("ERROR: No stored medication photos were found in the database for this patient")
        return

    analyzer = MedScanAnalyzer(reference_images=reference_images)
    print(f"Analyzer ready with {len(reference_images)} reference photo(s). Processing medication images...\n")

    # Find all .jpg/.png files recursively
    image_files = list(med_dir.glob("**/*.jpg")) + list(med_dir.glob("**/*.png"))
    if not image_files:
        print(f"No images found in {med_dir}")
        return

    print(f"Found {len(image_files)} image(s) to process.\n")

    for img_idx, img_path in enumerate(image_files, 1):
        # Display relative path safely
        try:
            display_path = img_path.relative_to(Path.cwd())
        except ValueError:
            display_path = img_path
        print(f"\n[{img_idx}/{len(image_files)}] Processing: {display_path}")
        try:
            result = analyzer.analyze(str(img_path))
            primary = result.get("primary_detection")
            summary = result.get("summary_text") or result.get("status", "No detection")
            
            print(f"  Status: {summary}")
            if primary:
                print(f"  → Detected: {primary.get('name', 'Unknown')} (confidence: {int(primary.get('confidence', 0)*100)}%)")
            
            ocr = result.get("ocr_text")
            if ocr:
                ocr_lines = ocr.strip().split("\n")[:2]
                print(f"  → OCR text: {' | '.join(ocr_lines)}")
        
        except Exception as exc:
            print(f"  ERROR: {exc}")

    print(f"\n\nDetection complete for patient {patient_id}.")


def run_camera_detection(patient_id: str = None):
    """Run live camera detection with real-time overlay."""
    print("Initializing MedScan analyzer (this may take a moment)...")
    analyzer = None
    reference_images = None

    if patient_id:
        print(f"Loading patient {patient_id} medication references from database...")
        reference_images = asyncio.run(_load_patient_reference_images_from_db(patient_id))
        if not reference_images:
            print("ERROR: No stored medication photos were found for this patient in the database.")
            return
        analyzer = MedScanAnalyzer(reference_images=reference_images)
    else:
        analyzer = get_medscan_analyzer()
    
    if patient_id:
        print(f"Using {len(reference_images or [])} database medication reference photo(s) for patient: {patient_id}")
    print("Camera ready. Press 'q' to quit.\n")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Unable to open camera index 0. Try another device or check permissions.")
        return

    try:
        frame_count = 0
        last_detection_time = 0
        detection_interval = 0.5  # Run detection every 0.5 seconds
        last_result = None

        while True:
            ret, frame = cap.read()
            if not ret:
                print("ERROR: Failed to read frame from camera")
                break

            frame_count += 1
            display = frame.copy()
            current_time = time.time()

            # Run detection at intervals to improve performance
            if current_time - last_detection_time >= detection_interval:
                last_detection_time = current_time
                
                # Save frame to temp file
                temp_dir = Path(tempfile.gettempdir()) / "medscan_camera"
                temp_dir.mkdir(parents=True, exist_ok=True)
                temp_path = temp_dir / f"frame_{int(time.time() * 1000)}.jpg"
                cv2.imwrite(str(temp_path), frame)

                try:
                    last_result = analyzer.analyze(str(temp_path))
                except Exception as exc:
                    print(f"Detection error: {exc}")

            # Draw detection results on display
            if last_result:
                draw_detection_overlay(display, last_result)

            # Draw status text
            cv2.putText(display, "Press 'q' to quit", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(display, f"Frame: {frame_count}", (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            
            cv2.imshow(SCREEN_WINDOW, display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("\nCamera closed.")
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="MedScan medication detection")
    parser.add_argument("--patient", type=str, help="Patient ID (for camera mode or batch processing)")
    parser.add_argument("--batch", action="store_true", help="Batch process stored medication photos instead of opening camera")
    
    args = parser.parse_args()

    if args.batch and args.patient:
        # Batch mode: process stored images
        process_patient_medications(args.patient)
    else:
        # Camera mode (default)
        run_camera_detection(patient_id=args.patient)


if __name__ == '__main__':
    main()
