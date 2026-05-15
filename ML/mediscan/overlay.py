"""
OpenCV drawing helpers for the MediScan HUD.
Supports simultaneous display of multiple medicine panels.
"""

from __future__ import annotations

import cv2
import numpy as np

from medicines import Medicine

GREEN      = (50, 205, 50)
RED        = (60, 60, 220)
WHITE      = (255, 255, 255)
BLACK      = (0, 0, 0)
DARK_PANEL = (20, 20, 20)
ACCENT     = (0, 165, 255)
CYAN       = (200, 220, 0)
YELLOW     = (0, 220, 220)

# Handle headless OpenCV (no GUI functions available)
try:
    FONT = cv2.FONT_HERSHEY_SIMPLEX
    LINE_AA = cv2.LINE_AA
except AttributeError:
    # In headless mode, we can't use cv2.putText anyway, so use dummy values
    FONT = 0
    LINE_AA = 0

# Colours cycled per-medicine so boxes/panels are visually distinct
_PALETTE = [GREEN, CYAN, YELLOW, (200, 100, 255), (100, 200, 255)]


def _color(index: int) -> tuple[int, int, int]:
    return _PALETTE[index % len(_PALETTE)]


# ── Bounding box ─────────────────────────────────────────────────────────

def draw_bounding_box(
    frame: np.ndarray,
    bbox: tuple[int, int, int, int],
    confidence: float,
    medicine_key: str = "",
    color_index: int = 0,
) -> None:
    x, y, w, h = bbox
    color = _color(color_index)

    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 1)
    arm, thick = min(w, h) // 6, 3
    for pt, h_end, v_end in [
        ((x,     y),     (x + arm, y),         (x,     y + arm)),
        ((x + w, y),     (x + w - arm, y),     (x + w, y + arm)),
        ((x,     y + h), (x + arm, y + h),     (x,     y + h - arm)),
        ((x + w, y + h), (x + w - arm, y + h), (x + w, y + h - arm)),
    ]:
        cv2.line(frame, pt, h_end, color, thick)
        cv2.line(frame, pt, v_end, color, thick)

    label = f"{medicine_key}  {confidence * 100:.0f}%"
    (lw, lh), _ = cv2.getTextSize(label, FONT, 0.48, 1)
    cv2.rectangle(frame, (x, y - lh - 8), (x + lw + 8, y), color, -1)
    cv2.putText(frame, label, (x + 4, y - 4), FONT, 0.48, BLACK, 1, cv2.LINE_AA)


# ── Multi-medicine panel stack ────────────────────────────────────────────

def draw_medicine_panels(
    frame: np.ndarray,
    medicines: list[tuple[str, Medicine | None]],
) -> None:
    """
    1 medicine  → full detailed panel (all fields, description, warnings).
    2+ medicines → compact panels stacked vertically on the right side.
    """
    if not medicines:
        return

    if len(medicines) == 1:
        key, medicine = medicines[0]
        _draw_detailed_panel(frame, medicine, key, _color(0))
        return

    fh, fw = frame.shape[:2]
    panel_w = 310
    margin = 10
    total_h = fh - 2 * margin
    panel_h = total_h // len(medicines)
    px = fw - panel_w - margin

    for idx, (key, medicine) in enumerate(medicines):
        py = margin + idx * panel_h
        _draw_single_panel(frame, medicine, key, px, py, panel_w, panel_h - 4, _color(idx))


def _draw_detailed_panel(
    frame: np.ndarray,
    medicine: Medicine | None,
    key: str,
    color: tuple[int, int, int],
) -> None:
    """Full-height detailed panel used when exactly one medicine is detected."""
    fh, fw = frame.shape[:2]
    panel_w = 320
    px, py = fw - panel_w - 12, 12
    ph = fh - 24

    overlay = frame.copy()
    cv2.rectangle(overlay, (px, py), (px + panel_w, py + ph), DARK_PANEL, -1)
    cv2.addWeighted(overlay, 0.82, frame, 0.18, 0, frame)
    cv2.rectangle(frame, (px, py), (px + panel_w, py + ph), color, 1)

    # Header bar
    cv2.rectangle(frame, (px, py), (px + panel_w, py + 40), color, -1)
    cv2.putText(frame, "MEDICINE DETECTED", (px + 8, py + 26), FONT, 0.52, BLACK, 1, cv2.LINE_AA)

    if medicine is None:
        cv2.putText(frame, key.upper(), (px + 8, py + 70), FONT, 0.55, WHITE, 1, cv2.LINE_AA)
        cv2.putText(frame, "No details in database", (px + 8, py + 96), FONT, 0.42, RED, 1, cv2.LINE_AA)
        return

    fields: list[tuple[str, str]] = [
        ("Name",         medicine["name"]),
        ("Generic",      medicine["generic_name"]),
        ("Category",     medicine["category"]),
        ("Form",         medicine["dosage_form"]),
        ("Strength",     medicine["strength"]),
        ("Manufacturer", medicine["manufacturer"]),
    ]

    ty = py + 62
    for label, value in fields:
        cv2.putText(frame, label.upper(), (px + 10, ty), FONT, 0.38, ACCENT, 1, cv2.LINE_AA)
        ty += 16
        for line in _wrap(value, 36):
            cv2.putText(frame, line, (px + 10, ty), FONT, 0.46, WHITE, 1, cv2.LINE_AA)
            ty += 18
        ty += 4

    # Description
    cv2.line(frame, (px + 10, ty), (px + panel_w - 10, ty), ACCENT, 1)
    ty += 12
    cv2.putText(frame, "DESCRIPTION", (px + 10, ty), FONT, 0.38, ACCENT, 1, cv2.LINE_AA)
    ty += 16
    for line in _wrap(medicine["description"], 36):
        cv2.putText(frame, line, (px + 10, ty), FONT, 0.42, WHITE, 1, cv2.LINE_AA)
        ty += 17
    ty += 6

    # Warning
    cv2.line(frame, (px + 10, ty), (px + panel_w - 10, ty), RED, 1)
    ty += 12
    cv2.putText(frame, "WARNING", (px + 10, ty), FONT, 0.38, RED, 1, cv2.LINE_AA)
    ty += 16
    for line in _wrap(medicine["warnings"], 36):
        cv2.putText(frame, line, (px + 10, ty), FONT, 0.42, (100, 100, 255), 1, cv2.LINE_AA)
        ty += 17


def _draw_single_panel(
    frame: np.ndarray,
    medicine: Medicine | None,
    key: str,
    px: int, py: int,
    pw: int, ph: int,
    color: tuple[int, int, int],
) -> None:
    # Background
    overlay = frame.copy()
    cv2.rectangle(overlay, (px, py), (px + pw, py + ph), DARK_PANEL, -1)
    cv2.addWeighted(overlay, 0.82, frame, 0.18, 0, frame)
    cv2.rectangle(frame, (px, py), (px + pw, py + ph), color, 1)

    # Header
    cv2.rectangle(frame, (px, py), (px + pw, py + 34), color, -1)
    name = medicine["name"] if medicine else key.upper()
    cv2.putText(frame, name.upper(), (px + 6, py + 22), FONT, 0.50, BLACK, 1, cv2.LINE_AA)

    if medicine is None:
        cv2.putText(frame, "No details in database", (px + 8, py + 54), FONT, 0.42, WHITE, 1, cv2.LINE_AA)
        return

    fields: list[tuple[str, str]] = [
        ("Generic",  medicine["generic_name"]),
        ("Category", medicine["category"]),
        ("Form",     medicine["dosage_form"]),
        ("Strength", medicine["strength"]),
        ("Mfr",      medicine["manufacturer"]),
    ]

    ty = py + 48
    max_ty = py + ph - 40   # leave room for warning at bottom

    for label, value in fields:
        if ty >= max_ty:
            break
        cv2.putText(frame, label.upper(), (px + 8, ty), FONT, 0.34, ACCENT, 1, cv2.LINE_AA)
        ty += 14
        for line in _wrap(value, 38):
            if ty >= max_ty:
                break
            cv2.putText(frame, line, (px + 8, ty), FONT, 0.40, WHITE, 1, cv2.LINE_AA)
            ty += 16
        ty += 2

    # Warning strip at bottom of panel
    warn_y = py + ph - 32
    cv2.line(frame, (px + 6, warn_y), (px + pw - 6, warn_y), RED, 1)
    cv2.putText(frame, "WARN:", (px + 8, warn_y + 14), FONT, 0.34, RED, 1, cv2.LINE_AA)
    warn_text = medicine["warnings"][:55]
    cv2.putText(frame, warn_text, (px + 50, warn_y + 14), FONT, 0.34, (120, 120, 255), 1, cv2.LINE_AA)


# ── OCR badge ────────────────────────────────────────────────────────────

def draw_ocr_badge(frame: np.ndarray, raw_text: str) -> None:
    fh, fw = frame.shape[:2]
    text = f"OCR: {raw_text[:60]}"
    (tw, th), _ = cv2.getTextSize(text, FONT, 0.42, 1)
    bx, by = 10, fh - 42
    cv2.rectangle(frame, (bx - 4, by - th - 4), (bx + tw + 4, by + 4), DARK_PANEL, -1)
    cv2.rectangle(frame, (bx - 4, by - th - 4), (bx + tw + 4, by + 4), CYAN, 1)
    cv2.putText(frame, text, (bx, by), FONT, 0.42, CYAN, 1, cv2.LINE_AA)


# ── Status bar ───────────────────────────────────────────────────────────

def draw_status_bar(
    frame: np.ndarray,
    fps: float,
    status: str,
    ref_count: int,
) -> None:
    fh, fw = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, fh - 28), (fw, fh), DARK_PANEL, -1)
    cv2.addWeighted(overlay, 0.9, frame, 0.1, 0, frame)
    cv2.line(frame, (0, fh - 28), (fw, fh - 28), GREEN, 1)
    left = f"  FPS: {fps:.1f}   Refs: {ref_count}   [Q]Quit [R]Reload [S]Speech [D]Debug"
    (rw, _), _ = cv2.getTextSize(status, FONT, 0.40, 1)
    cv2.putText(frame, left, (8, fh - 8), FONT, 0.40, WHITE, 1, cv2.LINE_AA)
    cv2.putText(frame, status, (fw - rw - 8, fh - 8), FONT, 0.40, WHITE, 1, cv2.LINE_AA)


# ── Scanning indicator ───────────────────────────────────────────────────

def draw_scanning_indicator(frame: np.ndarray, tick: int) -> None:
    fh, fw = frame.shape[:2]
    alpha = abs((tick % 60) - 30) / 30.0
    color = tuple(int(c * alpha) for c in GREEN)
    label = "SCANNING..."
    (lw, _), _ = cv2.getTextSize(label, FONT, 0.7, 2)
    cv2.putText(frame, label, ((fw - lw) // 2, 44), FONT, 0.7, color, 2, cv2.LINE_AA)  # type: ignore[arg-type]


# ── No references warning ────────────────────────────────────────────────

def draw_no_references_warning(frame: np.ndarray) -> None:
    fh, fw = frame.shape[:2]
    lines = [
        "No reference images found.",
        "Add photos to  reference_images/",
        "and name them after the medicine key.",
        "Example:  reference_images/paracetamol.jpg",
    ]
    start_y = (fh - len(lines) * 32) // 2
    for i, line in enumerate(lines):
        (lw, _), _ = cv2.getTextSize(line, FONT, 0.62, 1)
        cv2.putText(frame, line, ((fw - lw) // 2, start_y + i * 32), FONT, 0.62, RED, 1, cv2.LINE_AA)


# ── Debug scores ─────────────────────────────────────────────────────────

def draw_debug_scores(
    frame: np.ndarray,
    orb_scores: dict[str, float],
    consecutive: int,
    candidate: str | None,
    ocr_result: object | None,
) -> None:
    from ocr_reader import OcrResult
    if not orb_scores:
        return

    row_h = 22
    panel_h = (len(orb_scores) + 3) * row_h + 20
    panel_w = 280
    overlay = frame.copy()
    cv2.rectangle(overlay, (8, 8), (8 + panel_w, 8 + panel_h), DARK_PANEL, -1)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
    cv2.rectangle(frame, (8, 8), (8 + panel_w, 8 + panel_h), ACCENT, 1)

    y = 26
    cv2.putText(frame, "DEBUG — MATCH SCORES", (14, y), FONT, 0.40, ACCENT, 1, cv2.LINE_AA)
    y += row_h
    ocr_txt = f"OCR: {ocr_result.medicine_key} ({ocr_result.confidence:.2f})" if isinstance(ocr_result, OcrResult) else "OCR: —"  # type: ignore[union-attr]
    cv2.putText(frame, ocr_txt, (14, y), FONT, 0.38, CYAN, 1, cv2.LINE_AA)
    y += row_h + 4

    bar_max = panel_w - 120
    for key, score in sorted(orb_scores.items(), key=lambda x: -x[1]):
        bar_len = int(bar_max * min(score, 1.0))
        cv2.rectangle(frame, (14, y - 12), (14 + bar_max, y + 4), (50, 50, 50), -1)
        if bar_len > 0:
            bar_color = GREEN if score >= 0.40 else ACCENT
            cv2.rectangle(frame, (14, y - 12), (14 + bar_len, y + 4), bar_color, -1)
        cv2.putText(frame, f"{key[:16]:<16} {score:.2f}", (16, y), FONT, 0.38, WHITE, 1, cv2.LINE_AA)
        y += row_h


# ── Internal ─────────────────────────────────────────────────────────────

def _wrap(text: str, max_chars: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current = (current + " " + word).strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]
