"""Image quality pipeline (refactored from the notebook).

Differences from the notebook, and why:
  * Models are loaded once and reused (loading per request would take seconds).
  * Images are analysed from memory (no temp files, safe for concurrent requests).
  * The rule thresholds and scoring logic are unchanged.
"""
import threading
import cv2
import numpy as np
import torch
import pyiqa

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
IQA_MAX_SIDE = 1600  # downscale only for the neural metrics, to bound CPU time

_models = {}
_lock = threading.Lock()  # torch models are not guaranteed thread-safe


def load_models():
    if not _models:
        _models["brisque"] = pyiqa.create_metric("brisque", device=DEVICE)
        _models["musiq"] = pyiqa.create_metric("musiq", device=DEVICE)
    return _models


def _to_tensor(bgr: np.ndarray) -> torch.Tensor:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    longest = max(h, w)
    if longest > IQA_MAX_SIDE:
        s = IQA_MAX_SIDE / longest
        rgb = cv2.resize(rgb, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    t = torch.from_numpy(rgb).float().div(255.0).permute(2, 0, 1).unsqueeze(0)
    return t.to(DEVICE)


# ---- classical metrics (identical to the notebook) ----
def detect_blur(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def detect_brightness(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray))


def detect_exposure(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return {
        "dark_percentage": float(np.mean(gray < 20) * 100),
        "bright_percentage": float(np.mean(gray > 235) * 100),
    }


def detect_noise(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    residual = gray.astype(np.float32) - blurred.astype(np.float32)
    return float(np.mean(np.abs(residual)))


def evaluate_image_quality(image: np.ndarray) -> dict:
    """image: BGR uint8 array. Returns the API payload plus raw metrics."""
    models = load_models()
    tensor = _to_tensor(image)
    with _lock, torch.no_grad():
        brisque_score = float(models["brisque"](tensor).item())
        musiq_score = float(models["musiq"](tensor).item())

    sharpness_val = detect_blur(image)
    brightness_val = detect_brightness(image)
    exposure = detect_exposure(image)
    noise_val = detect_noise(image)

    issues = []

    # A. Blur
    if sharpness_val < 80:
        severity = "high" if sharpness_val < 35 else "medium"
        confidence = min(0.95, max(0.5, (100 - sharpness_val) / 100.0))
        issues.append({"type": "blur", "severity": severity, "confidence": round(float(confidence), 2)})
    elif sharpness_val < 150:
        issues.append({"type": "blur", "severity": "low",
                       "confidence": round(float((150 - sharpness_val) / 150.0), 2)})

    # B. Noise
    if noise_val > 5.0:
        severity = "high" if noise_val > 15.0 else "medium"
        confidence = min(0.99, noise_val / 25.0)
        issues.append({"type": "noise", "severity": severity, "confidence": round(float(confidence), 2)})
    elif noise_val > 2.0:
        issues.append({"type": "noise", "severity": "low",
                       "confidence": round(float(min(1.0, noise_val / 5.0)), 2)})

    # C. Exposure
    dark_pct, bright_pct = exposure["dark_percentage"], exposure["bright_percentage"]
    if dark_pct > 30.0:
        severity = "high" if dark_pct > 60.0 else "medium"
        issues.append({"type": "underexposure", "severity": severity,
                       "confidence": round(float(min(0.95, dark_pct / 100.0)), 2)})
    if bright_pct > 30.0:
        severity = "high" if bright_pct > 60.0 else "medium"
        issues.append({"type": "overexposure", "severity": severity,
                       "confidence": round(float(min(0.95, bright_pct / 100.0)), 2)})

    # Score: MUSIQ anchor minus penalties
    quality_score = int(np.clip(musiq_score, 0, 100))
    for issue in issues:
        quality_score -= {"high": 25, "medium": 12, "low": 5}[issue["severity"]]
    quality_score = int(np.clip(quality_score, 0, 100))

    if quality_score >= 70:
        label = "ACCEPTABLE"
    elif quality_score >= 40:
        label = "DEGRADED"
    else:
        label = "DEFECTIVE"

    return {
        "quality_score": quality_score,
        "quality_label": label,
        "issues": issues,
        "metrics": {
            "brisque_score": brisque_score,
            "musiq_score": musiq_score,
            "sharpness": sharpness_val,
            "brightness": brightness_val,
            "noise": noise_val,
            "dark_pixel_percentage": dark_pct,
            "bright_pixel_percentage": bright_pct,
        },
    }
