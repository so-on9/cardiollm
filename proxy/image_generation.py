# Image generation backends and prompt construction for CardioLLM.
import base64
import os
import secrets
import time
from pathlib import Path

import requests
from pydantic import BaseModel, Field

from structured_json import PART_LABELS


BASE_DIR = Path(__file__).resolve().parent
IMAGE_BACKEND = os.environ.get("IMAGE_BACKEND", "mock").strip().lower()
IMAGE_API_URL = os.environ.get("IMAGE_API_URL", "").rstrip("/")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "Stable Diffusion 1.5")
COMFYUI_CHECKPOINT = os.environ.get("COMFYUI_CHECKPOINT", "v1-5-pruned-emaonly-fp16.safetensors")
COMFYUI_IMAGE_SIZE = int(os.environ.get("COMFYUI_IMAGE_SIZE", "512"))
COMFYUI_DENOISE = float(os.environ.get("COMFYUI_DENOISE", "0.45"))
GENERATED_DIR = BASE_DIR / "static" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
HEART_BASE_PATH = BASE_DIR / "static" / "assets" / "inpaint" / "heart_base.png"
HEART_MASK_DIR = BASE_DIR / "static" / "assets" / "inpaint" / "masks"


class ImageGenerateReq(BaseModel):
    structured: dict = Field(default_factory=dict)
    summary: str = ""
    source: str = ""
    region: str = "auto"
    condition: str = "auto"
    visual_strength: str = "clear"
    width: int = Field(ge=256, le=1536, default=1024)
    height: int = Field(ge=256, le=1536, default=1024)
    steps: int = Field(ge=1, le=80, default=24)
    cfg_scale: float = Field(ge=1.0, le=20.0, default=5.0)

IMAGE_CONDITION_TEXT = {
    "dilatation": "dilatation / enlargement",
    "hypertrophy": "hypertrophy / thickened myocardium",
    "stenosis": "stenosis",
    "regurgitation": "regurgitation",
    "dysfunction": "functional abnormality",
    "pressure_elevation": "pressure elevation",
    "aneurysm": "aneurysm",
    "hypokinesia": "hypokinesia",
    "normal": "normal",
    "other": "other abnormal finding",
}

SEVERITY_TEXT = {
    "trace": "trace",
    "mild": "mild",
    "moderate": "moderate",
    "severe": "severe",
    "unknown": "",
}

IMAGE_MASK_REGIONS = {
    "AO": {"filename": "aorta.png", "label": "主動脈", "prompt": "aorta"},
    "PA": {"filename": "pulmonary_artery.png", "label": "肺動脈", "prompt": "pulmonary artery"},
    "LA": {"filename": "left_atrium.png", "label": "左心房", "prompt": "left atrium"},
    "LV": {"filename": "left_ventricle.png", "label": "左心室", "prompt": "left ventricle"},
    "RA": {"filename": "right_atrium.png", "label": "右心房", "prompt": "right atrium"},
    "RV": {"filename": "right_ventricle.png", "label": "右心室", "prompt": "right ventricle"},
    "MV": {"filename": "mitral_valve.png", "label": "二尖瓣", "prompt": "mitral valve"},
    "TV": {"filename": "tricuspid_valve.png", "label": "三尖瓣", "prompt": "tricuspid valve"},
    "SVC": {"filename": "superior_vena_cava.png", "label": "上腔靜脈", "prompt": "superior vena cava"},
    "IVC": {"filename": "inferior_vena_cava.png", "label": "下腔靜脈", "prompt": "inferior vena cava"},
}


def build_image_prompt(structured: dict, summary: str = "") -> str:
    findings = structured.get("findings") if isinstance(structured, dict) else []
    finding_text: list[str] = []
    for item in findings or []:
        if not isinstance(item, dict) or item.get("status") == "absent":
            continue
        part = item.get("part_name") or PART_LABELS.get(str(item.get("part") or "").upper(), item.get("part") or "heart")
        severity = SEVERITY_TEXT.get(str(item.get("severity") or "unknown"), "")
        condition = IMAGE_CONDITION_TEXT.get(str(item.get("condition") or "other"), "other abnormal finding")
        finding_text.append(" ".join(x for x in [severity, str(part), condition] if x).strip())
    if not finding_text:
        finding_text.append("echocardiography report findings summarized as a clean heart anatomy illustration")

    return (
        "Clean clinical medical illustration of the human heart, front cutaway anatomy, "
        "professional hospital diagram style, clear anatomical structures, subtle labels, "
        "white or transparent background, accurate proportions, no gore, no photorealism. "
        "Highlight these findings: " + "; ".join(finding_text[:10]) + "."
    )


def build_negative_image_prompt() -> str:
    return (
        "cartoon, fantasy, horror, gore, blood, distorted anatomy, extra organs, wrong labels, "
        "illegible text, watermark, logo, low quality, blurry, noisy, photorealistic surgery, "
        "blue discoloration, cyan stains, colored patches, spots, plaque, lesions, bubbles, "
        "rash-like texture, paint overlay, heatmap, disease marks, artificial tint"
    )


def save_generated_image(image_b64: str) -> str:
    raw = image_b64.split(",", 1)[-1]
    data = base64.b64decode(raw)
    name = f"heart_ai_{int(time.time() * 1000)}.png"
    path = GENERATED_DIR / name
    path.write_bytes(data)
    return f"/static/generated/{name}"


def save_generated_bytes(data: bytes) -> str:
    name = f"heart_ai_{int(time.time() * 1000)}.png"
    path = GENERATED_DIR / name
    path.write_bytes(data)
    return f"/static/generated/{name}"


def select_mask_region(structured: dict, requested: str) -> str | None:
    requested_key = (requested or "auto").strip().upper()
    if requested_key != "AUTO":
        return requested_key if requested_key in IMAGE_MASK_REGIONS else None
    findings = structured.get("findings") if isinstance(structured, dict) else []
    for item in findings or []:
        if not isinstance(item, dict) or item.get("status") == "absent":
            continue
        part = str(item.get("part") or "").upper()
        if part in IMAGE_MASK_REGIONS:
            return part
    return None


def resolve_visual_condition(structured: dict, region_key: str, requested: str) -> tuple[str, str]:
    requested_value = (requested or "auto").strip().lower()
    findings = structured.get("findings") if isinstance(structured, dict) else []
    for item in findings or []:
        if not isinstance(item, dict) or item.get("status") == "absent":
            continue
        if str(item.get("part") or "").upper() != region_key:
            continue
        condition = str(item.get("condition") or "other")
        severity = str(item.get("severity") or "unknown")
        if requested_value == "auto" and condition in IMAGE_CONDITION_TEXT:
            return condition, severity
        if requested_value == condition and condition in IMAGE_CONDITION_TEXT:
            return condition, severity
    if requested_value in IMAGE_CONDITION_TEXT and requested_value not in {"normal", "other"}:
        return requested_value, "unknown"
    return "dilatation", "unknown"


def build_masked_image_prompt(structured: dict, region_key: str, requested_condition: str, visual_strength: str) -> tuple[str, str]:
    region = IMAGE_MASK_REGIONS[region_key]
    condition, severity = resolve_visual_condition(structured, region_key, requested_condition)
    condition_text = IMAGE_CONDITION_TEXT.get(condition, "abnormality")
    severity_text = SEVERITY_TEXT.get(severity, "")
    strength_text = "clearly visible" if visual_strength == "clear" else "subtle"
    action_text = {
        "dilatation": "Subtly expand the anatomical contour into the allowed masked margin while keeping the same pink, red and beige heart tissue palette; do not add spots, stains, plaques, lesions or blue coloration.",
        "hypertrophy": "Subtly thicken the muscular wall while keeping the same pink, red and beige heart tissue palette and the chamber recognizable.",
        "stenosis": "Subtly narrow the affected anatomical opening while preserving surrounding anatomy and the original color palette.",
        "regurgitation": "Show a very restrained backward-flow cue only if it matches the original illustration palette; do not add blue stains or disease marks.",
        "dysfunction": "Use only subtle anatomical emphasis without changing color palette or adding lesion-like texture.",
        "pressure_elevation": "Show restrained visual prominence of this vascular structure without colored overlays or spots.",
    }.get(condition, "Make the abnormality visible while preserving surrounding anatomy.")
    finding = " ".join(word for word in (severity_text, condition_text) if word)
    return (
        "Edit only the permitted anatomical region in the supplied heart cutaway illustration. "
        "Preserve the original medical illustration style, black linework, lighting, texture and all structures outside the edit region. "
        "Keep the natural pink, red, beige and white heart anatomy color palette. "
        f"In the {region['prompt']}, depict a {strength_text} {finding}. {action_text} "
        "No labels, arrows, text, colored overlays, blue areas, spots, lesions, additional organs or background changes.",
        condition,
    )


def upload_comfyui_input(path: Path, filename: str) -> str:
    if not IMAGE_API_URL:
        raise RuntimeError("IMAGE_API_URL is not configured")
    if not path.exists():
        raise RuntimeError(f"Missing image asset: {path.name}")
    with path.open("rb") as image_file:
        response = requests.post(
            f"{IMAGE_API_URL}/upload/image",
            files={"image": (filename, image_file, "image/png")},
            data={"type": "input", "subfolder": "cardiollm", "overwrite": "true"},
            timeout=60,
        )
    if response.status_code != 200:
        raise RuntimeError(f"ComfyUI upload failed: {response.text}")
    uploaded = response.json()
    name = uploaded.get("name") or filename
    subfolder = uploaded.get("subfolder") or ""
    return f"{subfolder}/{name}" if subfolder else name


def build_comfyui_masked_workflow(req: ImageGenerateReq, prompt: str, negative_prompt: str, base_image: str, mask_image: str, condition: str) -> tuple[dict, int, int, float]:
    size = max(256, min(768, COMFYUI_IMAGE_SIZE))
    size -= size % 8
    clear = req.visual_strength == "clear"
    expand = (32 if clear else 16) if condition == "dilatation" else (6 if clear else 2)
    denoise = COMFYUI_DENOISE
    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": COMFYUI_CHECKPOINT}},
        "2": {"class_type": "LoadImage", "inputs": {"image": base_image}},
        "3": {"class_type": "ImageScale", "inputs": {"image": ["2", 0], "upscale_method": "lanczos", "width": size, "height": size, "crop": "disabled"}},
        "3m": {"class_type": "MaskToImage", "inputs": {"mask": ["2", 1]}},
        "3ms": {"class_type": "ImageScale", "inputs": {"image": ["3m", 0], "upscale_method": "lanczos", "width": size, "height": size, "crop": "disabled"}},
        "3ma": {"class_type": "ImageToMask", "inputs": {"image": ["3ms", 0], "channel": "red"}},
        "4": {"class_type": "LoadImageMask", "inputs": {"image": mask_image, "channel": "red"}},
        "5": {"class_type": "MaskToImage", "inputs": {"mask": ["4", 0]}},
        "6": {"class_type": "ImageScale", "inputs": {"image": ["5", 0], "upscale_method": "lanczos", "width": size, "height": size, "crop": "disabled"}},
        "7": {"class_type": "ImageToMask", "inputs": {"image": ["6", 0], "channel": "red"}},
        "7g": {"class_type": "GrowMask", "inputs": {"mask": ["7", 0], "expand": expand, "tapered_corners": True}},
        "8": {"class_type": "VAEEncodeForInpaint", "inputs": {"pixels": ["3", 0], "vae": ["1", 2], "mask": ["7", 0], "grow_mask_by": expand}},
        "10": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "11": {"class_type": "CLIPTextEncode", "inputs": {"text": negative_prompt, "clip": ["1", 1]}},
        "12": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "seed": secrets.randbits(63), "steps": req.steps, "cfg": req.cfg_scale, "sampler_name": "dpmpp_2m", "scheduler": "karras", "positive": ["10", 0], "negative": ["11", 0], "latent_image": ["8", 0], "denoise": denoise}},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["1", 2]}},
        "14": {"class_type": "ImageCompositeMasked", "inputs": {"destination": ["3", 0], "source": ["13", 0], "x": 0, "y": 0, "resize_source": False, "mask": ["7g", 0]}},
        "15": {"class_type": "MaskComposite", "inputs": {"destination": ["3ma", 0], "source": ["7g", 0], "x": 0, "y": 0, "operation": "subtract"}},
        "16": {"class_type": "JoinImageWithAlpha", "inputs": {"image": ["14", 0], "alpha": ["15", 0]}},
        "17": {"class_type": "SaveImage", "inputs": {"filename_prefix": "cardiollm/heart_masked", "images": ["16", 0]}},
    }
    return workflow, size, expand, denoise


def generate_with_comfyui(req: ImageGenerateReq, prompt: str, negative_prompt: str, region_key: str, condition: str) -> dict:
    region = IMAGE_MASK_REGIONS[region_key]
    base_image = upload_comfyui_input(HEART_BASE_PATH, "heart_base.png")
    mask_image = upload_comfyui_input(HEART_MASK_DIR / region["filename"], region["filename"])
    workflow, size, expand, denoise = build_comfyui_masked_workflow(req, prompt, negative_prompt, base_image, mask_image, condition)
    response = requests.post(f"{IMAGE_API_URL}/prompt", json={"prompt": workflow, "client_id": "cardiollm"}, timeout=60)
    if response.status_code != 200:
        raise RuntimeError(f"ComfyUI queue failed: {response.text}")
    prompt_id = response.json().get("prompt_id")
    if not prompt_id:
        raise RuntimeError("ComfyUI returned no prompt_id")

    deadline = time.time() + 600
    output_image = None
    while time.time() < deadline:
        history = requests.get(f"{IMAGE_API_URL}/history/{prompt_id}", timeout=30).json().get(prompt_id)
        if history:
            status = history.get("status") or {}
            if status.get("status_str") == "error":
                raise RuntimeError("ComfyUI workflow execution failed")
            for output in (history.get("outputs") or {}).values():
                images = output.get("images") or []
                if images:
                    output_image = images[0]
                    break
            if output_image:
                break
        time.sleep(0.5)
    if not output_image:
        raise RuntimeError("Timed out waiting for ComfyUI output")

    view = requests.get(f"{IMAGE_API_URL}/view", params=output_image, timeout=60)
    if view.status_code != 200:
        raise RuntimeError(f"ComfyUI output download failed: {view.text}")
    return {
        "backend": "comfyui",
        "image_url": save_generated_bytes(view.content),
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "region": region_key,
        "region_label": region["label"],
        "size": size,
        "mode": "masked_img2img",
        "condition": condition,
        "mask_expand": expand,
        "denoise": denoise,
    }


def save_generated_pil(image) -> str:
    name = f"heart_ai_{int(time.time() * 1000)}.png"
    path = GENERATED_DIR / name
    image.save(path, format="PNG")
    return f"/static/generated/{name}"


def _clip_paste_rgba(destination, source, xy):
    x, y = xy
    dst_w, dst_h = destination.size
    src_w, src_h = source.size
    left = max(0, x)
    top = max(0, y)
    right = min(dst_w, x + src_w)
    bottom = min(dst_h, y + src_h)
    if left >= right or top >= bottom:
        return
    crop = source.crop((left - x, top - y, right - x, bottom - y))
    destination.alpha_composite(crop, (left, top))


LOCAL_WARP_REGION_CONFIG = {
    "AO": {
        "dilatation": {"trace": 1.04, "mild": 1.09, "moderate": 1.15, "severe": 1.23, "unknown": 1.12},
        "pad": 0.050,
        "feather": 0.011,
        "offset": 0.010,
        "offset_vector": [0.0, -0.75],
        "core_filter": 3,
        "highlight": [255, 170, 128, 58],
    },
    "PA": {
        "dilatation": {"trace": 1.04, "mild": 1.09, "moderate": 1.15, "severe": 1.23, "unknown": 1.12},
        "pad": 0.052,
        "feather": 0.011,
        "offset": 0.010,
        "offset_vector": [0.9, -0.35],
        "core_filter": 3,
        "highlight": [118, 190, 255, 54],
    },
    "LA": {
        "dilatation": {"trace": 1.08, "mild": 1.16, "moderate": 1.23, "severe": 1.32, "unknown": 1.20},
        "pad": 0.060,
        "feather": 0.014,
        "offset": 0.014,
        "offset_vector": [0.75, -0.45],
        "core_filter": 7,
        "highlight": [255, 196, 136, 48],
    },
    "RA": {
        "dilatation": {"trace": 1.10, "mild": 1.18, "moderate": 1.26, "severe": 1.34, "unknown": 1.22},
        "pad": 0.065,
        "feather": 0.011,
        "offset": 0.030,
        "offset_vector": [-1.0, 0.15],
        "core_filter": 5,
        "highlight": [255, 190, 130, 46],
    },
    "LV": {
        "dilatation": {"trace": 1.07, "mild": 1.15, "moderate": 1.23, "severe": 1.31, "unknown": 1.19},
        "pad": 0.060,
        "feather": 0.011,
        "offset": 0.022,
        "offset_vector": [0.45, 1.0],
        "core_filter": 5,
        "highlight": [255, 158, 126, 50],
        "hypertrophy": {"trace": 7, "mild": 11, "moderate": 21, "severe": 33, "unknown": 16},
        "hypertrophy_profile": {
            "trace": {"inner": 7, "outer": 3, "fill_alpha": 6, "edge_alpha": 18},
            "mild": {"inner": 11, "outer": 3, "fill_alpha": 8, "edge_alpha": 24},
            "moderate": {"inner": 30, "outer": 6, "fill_alpha": 12, "edge_alpha": 34},
            "severe": {"inner": 52, "outer": 9, "fill_alpha": 16, "edge_alpha": 46},
            "unknown": {"inner": 20, "outer": 5, "fill_alpha": 10, "edge_alpha": 30},
        },
        "hypertrophy_highlight": [255, 126, 94, 46],
        "hypertrophy_fill": [255, 150, 112, 16],
    },
    "RV": {
        "dilatation": {"trace": 1.04, "mild": 1.09, "moderate": 1.14, "severe": 1.20, "unknown": 1.12},
        "pad": 0.046,
        "feather": 0.010,
        "offset": 0.022,
        "offset_vector": [-0.95, 0.72],
        "core_filter": 5,
        "highlight": [255, 178, 132, 58],
        "hypertrophy": {"trace": 5, "mild": 8, "moderate": 15, "severe": 25, "unknown": 12},
        "hypertrophy_profile": {
            "trace": {"inner": 5, "outer": 2, "fill_alpha": 5, "edge_alpha": 16, "bias_strength": 0.78},
            "mild": {"inner": 8, "outer": 2, "fill_alpha": 7, "edge_alpha": 22, "bias_strength": 0.75},
            "moderate": {"inner": 22, "outer": 5, "fill_alpha": 11, "edge_alpha": 32, "bias_strength": 0.56},
            "severe": {"inner": 38, "outer": 7, "fill_alpha": 15, "edge_alpha": 44, "bias_strength": 0.34},
            "unknown": {"inner": 15, "outer": 4, "fill_alpha": 9, "edge_alpha": 28, "bias_strength": 0.60},
        },
        "hypertrophy_bias_vector": [-0.95, 0.72],
        "hypertrophy_highlight": [255, 130, 96, 44],
        "hypertrophy_fill": [255, 152, 112, 15],
    },
}

LOCAL_WARP_DEFAULT_CONFIG = {
    "dilatation": {"trace": 1.08, "mild": 1.16, "moderate": 1.24, "severe": 1.32, "unknown": 1.20},
    "pad": 0.065,
    "feather": 0.011,
    "offset": 0.022,
    "core_filter": 5,
    "highlight": [255, 180, 130, 42],
    "hypertrophy": {"trace": 5, "mild": 8, "moderate": 14, "severe": 22, "unknown": 11},
    "hypertrophy_profile": {
        "trace": {"inner": 5, "outer": 2, "fill_alpha": 5, "edge_alpha": 16},
        "mild": {"inner": 8, "outer": 2, "fill_alpha": 7, "edge_alpha": 22},
        "moderate": {"inner": 14, "outer": 4, "fill_alpha": 10, "edge_alpha": 30},
        "severe": {"inner": 22, "outer": 5, "fill_alpha": 14, "edge_alpha": 40},
        "unknown": {"inner": 11, "outer": 3, "fill_alpha": 8, "edge_alpha": 26},
    },
    "hypertrophy_highlight": [255, 136, 100, 42],
    "hypertrophy_fill": [255, 158, 118, 14],
}

LOCAL_HYPERTROPHY_SHAPE_CONFIG = {
    "LV": {
        "trace": {"shrink": 5, "push": 4, "alpha": 92, "source": 10},
        "mild": {"shrink": 8, "push": 6, "alpha": 110, "source": 12},
        "moderate": {"shrink": 22, "push": 14, "alpha": 142, "source": 22},
        "severe": {"shrink": 38, "push": 24, "alpha": 166, "source": 34},
        "unknown": {"shrink": 15, "push": 10, "alpha": 128, "source": 18},
        "chamber": {"cx": 0.52, "cy": 0.58, "rx": 0.31, "ry": 0.37},
        "directions": [
            {"source": [1.0, 0.10], "target": [-1.0, -0.06], "select": 0.82},
            {"source": [-1.0, -0.08], "target": [1.0, 0.04], "select": 0.70},
            {"source": [0.18, 1.0], "target": [-0.12, -1.0], "select": 0.58},
        ],
    },
    "RV": {
        "trace": {"shrink": 4, "push": 3, "alpha": 82, "source": 8},
        "mild": {"shrink": 6, "push": 5, "alpha": 100, "source": 10},
        "moderate": {"shrink": 17, "push": 11, "alpha": 136, "source": 18},
        "severe": {"shrink": 30, "push": 19, "alpha": 158, "source": 28},
        "unknown": {"shrink": 12, "push": 8, "alpha": 120, "source": 14},
        "chamber": {"cx": 0.46, "cy": 0.50, "rx": 0.35, "ry": 0.33},
        "directions": [
            {"source": [-1.0, 0.52], "target": [1.0, -0.28], "select": 0.92},
            {"source": [-1.0, 0.02], "target": [1.0, -0.02], "select": 0.78},
            {"source": [0.60, -0.06], "target": [-0.42, 0.03], "select": 0.38, "min_severity": "severe"},
        ],
    },
}

SEVERITY_RANK = {"trace": 0, "mild": 1, "moderate": 2, "severe": 3, "unknown": 1}


def _local_warp_config(region_key: str) -> dict:
    return LOCAL_WARP_REGION_CONFIG.get(region_key, LOCAL_WARP_DEFAULT_CONFIG)


def _local_warp_scale(region_key: str, severity: str, visual_strength: str) -> float:
    config = _local_warp_config(region_key)
    if visual_strength != "clear":
        return max(1.06, config["dilatation"].get(severity or "unknown", config["dilatation"]["unknown"]) - 0.08)
    return config["dilatation"].get(severity or "unknown", config["dilatation"]["unknown"])


def _odd_filter_size(value: int) -> int:
    value = max(3, int(value))
    return value if value % 2 else value + 1


def _ellipse_mask_from_bbox(size: int, bbox: tuple[int, int, int, int], chamber: dict):
    from PIL import Image, ImageDraw

    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    cx = x0 + w * float(chamber.get("cx", 0.5))
    cy = y0 + h * float(chamber.get("cy", 0.5))
    rx = max(4, w * float(chamber.get("rx", 0.3)))
    ry = max(4, h * float(chamber.get("ry", 0.35)))
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=255)
    return mask


def _shift_image_no_wrap(image, dx: float, dy: float, fill=None):
    from PIL import Image

    dx = int(round(dx))
    dy = int(round(dy))
    if dx == 0 and dy == 0:
        return image.copy()
    if fill is None:
        fill = (0, 0, 0, 0) if image.mode == "RGBA" else 0
    shifted = Image.new(image.mode, image.size, fill)
    width, height = image.size
    src_left = max(0, -dx)
    src_top = max(0, -dy)
    src_right = min(width, width - dx)
    src_bottom = min(height, height - dy)
    if src_left >= src_right or src_top >= src_bottom:
        return shifted
    dst_left = max(0, dx)
    dst_top = max(0, dy)
    crop = image.crop((src_left, src_top, src_right, src_bottom))
    shifted.paste(crop, (dst_left, dst_top))
    return shifted



def generate_with_local_dilatation_mesh(req: ImageGenerateReq, prompt: str, negative_prompt: str, region_key: str, severity: str, base, threshold, config: dict) -> dict:
    from PIL import Image, ImageFilter
    import cv2
    import numpy as np

    region = IMAGE_MASK_REGIONS[region_key]
    size = base.size[0]
    bbox = threshold.getbbox()
    if not bbox:
        raise RuntimeError(f"Empty mask: {region['filename']}")

    scale = _local_warp_scale(region_key, severity, req.visual_strength)
    effective_scale = scale
    x0, y0, x1, y1 = bbox
    pad = max(36, int(size * (config["pad"] + 0.070)))
    box = (max(0, x0 - pad), max(0, y0 - pad), min(size, x1 + pad), min(size, y1 + pad))
    crop = base.crop(box).convert("RGBA")
    crop_mask = threshold.crop(box).convert("L")
    w, h = crop.size
    cx = (x0 + x1) / 2 - box[0]
    cy = (y0 + y1) / 2 - box[1]

    crop_arr = np.asarray(crop).astype(np.float32)
    mask_arr = np.asarray(crop_mask).astype(np.uint8)

    dilate_px = max(5, int(size * 0.014))
    blur_px = max(11, int(size * 0.022))
    if blur_px % 2 == 0:
        blur_px += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_px * 2 + 1, dilate_px * 2 + 1))
    influence = cv2.dilate(mask_arr, kernel, iterations=1)
    influence = cv2.GaussianBlur(influence, (blur_px, blur_px), 0)
    influence_f = influence.astype(np.float32) / 255.0
    warp_influence = influence_f
    blend_influence = influence_f
    if region_key in {"LV", "RV"}:
        # Ventricular masks contain dense trabeculae and myocardium texture. Keep the
        # chamber interior nearly unchanged; place most deformation on the outer rim.
        effective_scale = 1.0 + (float(scale) - 1.0) * 0.78
        inner_px = max(5, int(size * 0.018))
        inner_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (inner_px * 2 + 1, inner_px * 2 + 1))
        eroded = cv2.erode(mask_arr, inner_kernel, iterations=1)
        dilated = cv2.dilate(mask_arr, inner_kernel, iterations=1)
        outer_band = cv2.subtract(dilated, mask_arr)
        edge_band = cv2.subtract(dilated, eroded)
        vent_blur = max(25, int(size * 0.040))
        if vent_blur % 2 == 0:
            vent_blur += 1
        outer_f = cv2.GaussianBlur(outer_band, (vent_blur, vent_blur), 0).astype(np.float32) / 255.0
        edge_f = cv2.GaussianBlur(edge_band, (vent_blur, vent_blur), 0).astype(np.float32) / 255.0
        warp_influence = np.maximum(outer_f * 1.15, edge_f * 0.34)
        blend_influence = np.maximum(outer_f * 1.00, edge_f * 0.26)

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    local_scale = 1.0 + (float(effective_scale) - 1.0) * warp_influence
    map_x = cx + (xx - cx) / local_scale
    map_y = cy + (yy - cy) / local_scale
    map_x = np.clip(map_x, 0, w - 1).astype(np.float32)
    map_y = np.clip(map_y, 0, h - 1).astype(np.float32)

    warped = cv2.remap(
        crop_arr,
        map_x,
        map_y,
        interpolation=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REFLECT_101,
    )

    # Blend with a continuous alpha field. This changes the masked anatomy and a small
    # neighboring margin together, while LV/RV keep their interior texture mostly intact.
    blend = np.clip(blend_influence * 1.10, 0.0, 1.0)[..., None]
    out_crop = crop_arr * (1.0 - blend) + warped * blend
    out_crop[..., 3] = np.maximum(crop_arr[..., 3], out_crop[..., 3])
    out_crop = np.clip(out_crop, 0, 255).astype(np.uint8)

    result = base.copy()
    result.alpha_composite(Image.fromarray(out_crop, "RGBA"), (box[0], box[1]))

    return {
        "backend": "local_warp",
        "image_url": save_generated_pil(result),
        "prompt": prompt + "\n\nLocal OpenCV warp: per-pixel smooth ROI deformation using original adjacent anatomy; no mesh grid, glow or pasted duplicate.",
        "negative_prompt": negative_prompt,
        "region": region_key,
        "region_label": region["label"],
        "size": size,
        "mode": "mask_local_cv2_warp",
        "condition": "dilatation",
        "warp_scale": round(scale, 3),
        "effective_warp_scale": round(effective_scale, 3),
        "warp_offset": [0, 0],
        "warp_config": {"pad": pad, "edge_mode": "opencv_remap", "dilate_px": dilate_px, "blur_px": blur_px, "ventricle_texture_preserve": region_key in {"LV", "RV"}, "ventricle_outer_rim_only": region_key in {"LV", "RV"}},
    }

def generate_with_local_hypertrophy(req: ImageGenerateReq, prompt: str, negative_prompt: str, region_key: str, severity: str, base, threshold, config: dict) -> dict:
    from PIL import Image, ImageChops, ImageFilter

    region = IMAGE_MASK_REGIONS[region_key]
    size = base.size[0]
    severity_key = severity or "unknown"
    shape_map = LOCAL_HYPERTROPHY_SHAPE_CONFIG.get(region_key, {})
    shape_profile = shape_map.get(severity_key, shape_map.get("unknown", {}))
    profile_map = config.get("hypertrophy_profile", LOCAL_WARP_DEFAULT_CONFIG["hypertrophy_profile"])
    profile = profile_map.get(severity_key, profile_map["unknown"])
    bbox = threshold.getbbox()
    if not bbox:
        raise RuntimeError(f"Empty mask: {region['filename']}")

    chamber = shape_map.get("chamber")
    if not chamber:
        chamber = {"cx": 0.5, "cy": 0.55, "rx": 0.30, "ry": 0.35}
    chamber_mask = _ellipse_mask_from_bbox(size, bbox, chamber)
    chamber_mask = ImageChops.multiply(chamber_mask, threshold)
    if not chamber_mask.getbbox():
        chamber_mask = threshold.filter(ImageFilter.MinFilter(_odd_filter_size(21)))

    shrink_width = int(shape_profile.get("shrink", 10))
    push_distance = int(shape_profile.get("push", 8))
    shape_alpha = int(shape_profile.get("alpha", 110))
    source_width = int(shape_profile.get("source", 12))
    if req.visual_strength != "clear":
        shrink_width = max(3, int(shrink_width * 0.72))
        push_distance = max(2, int(push_distance * 0.72))
        shape_alpha = max(50, int(shape_alpha * 0.78))
        source_width = max(5, int(source_width * 0.72))

    shrink_filter = _odd_filter_size(shrink_width)
    source_filter = _odd_filter_size(source_width)
    blur_radius = max(1, int(size * 0.003))

    preserved_chamber = chamber_mask.filter(ImageFilter.MinFilter(shrink_filter))
    chamber_shrink_band = ImageChops.subtract(chamber_mask, preserved_chamber)
    chamber_shrink_band = chamber_shrink_band.filter(ImageFilter.GaussianBlur(blur_radius))

    outside_chamber_ring = ImageChops.subtract(
        chamber_mask.filter(ImageFilter.MaxFilter(source_filter)),
        chamber_mask,
    )
    outside_chamber_ring = ImageChops.multiply(outside_chamber_ring, threshold)
    outside_chamber_ring = outside_chamber_ring.filter(ImageFilter.GaussianBlur(blur_radius))

    # A very restrained edge cue is allowed, but the visible grade should still be readable
    # from chamber narrowing when this overlay is removed.
    edge_hint = chamber_shrink_band.point(lambda px: min(px, int(profile.get("edge_alpha", 18))))

    def direction_alpha(alpha_image, vector, strength):
        if not vector or strength <= 0 or not bbox:
            return alpha_image
        vx, vy = float(vector[0]), float(vector[1])
        norm = max(0.001, (vx * vx + vy * vy) ** 0.5)
        vx, vy = vx / norm, vy / norm
        x0, y0, x1, y1 = bbox
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        half_w, half_h = max(1, (x1 - x0) / 2), max(1, (y1 - y0) / 2)
        src = alpha_image.load()
        biased = Image.new("L", alpha_image.size, 0)
        dst = biased.load()
        for y in range(y0, y1):
            for x in range(x0, x1):
                value = src[x, y]
                if not value:
                    continue
                dx = (x - cx) / half_w
                dy = (y - cy) / half_h
                dot = max(-1.0, min(1.0, dx * vx + dy * vy))
                directional = (dot + 1.0) / 2.0
                weight = (1.0 - strength) + strength * directional
                dst[x, y] = int(value * weight)
        return biased

    result = base.copy()
    directions = shape_map.get("directions", [])
    severity_rank = SEVERITY_RANK.get(severity_key, SEVERITY_RANK["unknown"])
    used_directions = 0
    for direction in directions:
        min_severity = direction.get("min_severity")
        if min_severity and severity_rank < SEVERITY_RANK.get(min_severity, 0):
            continue
        source_alpha = direction_alpha(outside_chamber_ring, direction.get("source"), float(direction.get("select", 0.75)))
        tx, ty = direction.get("target", [0, 0])
        norm = max(0.001, (float(tx) * float(tx) + float(ty) * float(ty)) ** 0.5)
        tx, ty = float(tx) / norm, float(ty) / norm
        shifted_alpha = _shift_image_no_wrap(source_alpha, tx * push_distance, ty * push_distance, 0)
        shifted_alpha = ImageChops.multiply(shifted_alpha, chamber_shrink_band)
        shifted_alpha = shifted_alpha.point(lambda px, cap=shape_alpha: min(px, cap))
        if not shifted_alpha.getbbox():
            continue
        shifted_texture = _shift_image_no_wrap(base, tx * push_distance, ty * push_distance, (0, 0, 0, 0))
        shifted_texture.putalpha(ImageChops.multiply(shifted_texture.getchannel("A"), shifted_alpha))
        result = Image.alpha_composite(result, shifted_texture)
        used_directions += 1

    highlight_rgba = config.get("hypertrophy_highlight", LOCAL_WARP_DEFAULT_CONFIG["hypertrophy_highlight"])
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    highlight = Image.new("RGBA", base.size, tuple(highlight_rgba))
    highlight.putalpha(edge_hint)
    overlay = Image.alpha_composite(overlay, highlight)
    result = Image.alpha_composite(result, overlay)

    return {
        "backend": "local_warp",
        "image_url": save_generated_pil(result),
        "prompt": prompt + "\n\nLocal hypertrophy: chamber-boundary inward thickening only; outer contour, valves, vessels and apex are preserved.",
        "negative_prompt": negative_prompt,
        "region": region_key,
        "region_label": region["label"],
        "size": size,
        "mode": "mask_local_hypertrophy_chamber",
        "condition": "hypertrophy",
        "hypertrophy_band": shrink_width,
        "warp_offset": [0, 0],
        "warp_config": {
            "shrink_filter": shrink_filter,
            "source_filter": source_filter,
            "push_distance": push_distance,
            "shape_alpha": shape_alpha,
            "blur_radius": blur_radius,
            "chamber": chamber,
            "used_directions": used_directions,
        },
    }


LOCAL_EFFECT_CONDITIONS = {"stenosis", "regurgitation", "pressure_elevation", "dysfunction", "hypokinesia", "aneurysm"}
SEVERITY_STRENGTH = {"trace": 0.32, "mild": 0.48, "moderate": 0.72, "severe": 1.0, "unknown": 0.62}


def _mask_boundary(mask, width: int):
    from PIL import ImageChops, ImageFilter

    width = _odd_filter_size(width)
    outer = mask.filter(ImageFilter.MaxFilter(width))
    inner = mask.filter(ImageFilter.MinFilter(width))
    return ImageChops.subtract(outer, inner)


def _draw_polyline(draw, points, fill, width):
    if len(points) < 2:
        return
    for a, b in zip(points, points[1:]):
        draw.line((a, b), fill=fill, width=width, joint="curve")


def generate_with_local_condition_effect(req: ImageGenerateReq, prompt: str, negative_prompt: str, region_key: str, condition: str, severity: str, base, threshold, config: dict) -> dict:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    region = IMAGE_MASK_REGIONS[region_key]
    size = base.size[0]
    bbox = threshold.getbbox()
    if not bbox:
        raise RuntimeError(f"Empty mask: {region['filename']}")
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    strength = SEVERITY_STRENGTH.get(severity or "unknown", SEVERITY_STRENGTH["unknown"])
    if req.visual_strength != "clear":
        strength *= 0.72
    result = base.copy()
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    mode = f"mask_local_{condition}"

    if condition == "stenosis":
        severity_rank = SEVERITY_RANK.get(severity or "unknown", SEVERITY_RANK["unknown"])
        opening_fraction = {
            "trace": 0.62,
            "mild": 0.44,
            "moderate": 0.20,
            "severe": 0.055,
            "unknown": 0.30,
        }.get(severity or "unknown", 0.30)
        if region_key == "PA":
            opening_fraction = max(0.035, opening_fraction - (0.06 if severity_rank >= 2 else 0.02))
        elif region_key in {"MV", "TV"}:
            opening_fraction = max(0.04, opening_fraction - (0.04 if severity_rank >= 2 else 0.0))

        valve_targets = {
            "AO": {"cx": 0.70, "cy": 1.07, "rx": 0.29, "ry": 0.13, "jet": [0.12, -1.0], "kind": "aortic"},
            "PA": {"cx": 0.12, "cy": 1.08, "rx": 0.40, "ry": 0.38, "jet": [1.0, -0.24], "kind": "pulmonary"},
            "MV": {"cx": 0.50, "cy": 0.54, "rx": 0.42, "ry": 0.30, "jet": [-0.22, 1.0], "kind": "atrioventricular"},
            "TV": {"cx": 0.55, "cy": 0.42, "rx": 0.46, "ry": 0.30, "jet": [0.35, 1.0], "kind": "atrioventricular"},
        }
        target = valve_targets.get(region_key, {"cx": 0.50, "cy": 0.50, "rx": 0.32, "ry": 0.24, "jet": [0.0, -1.0], "kind": "generic"})
        vcx = x0 + w * float(target["cx"])
        vcy = y0 + h * float(target["cy"])
        vrx = max(9, w * float(target["rx"]))
        vry = max(7, h * float(target["ry"]))
        slit_w = max(1.0, vrx * 2 * opening_fraction)
        slit_h = max(1.0, vry * (0.22 if region_key in {"AO", "PA"} else 0.18))
        ring_width = max(2, int(size * (0.004 + 0.003 * strength)))
        leaflet_alpha = int(112 + 58 * strength)
        edge_alpha = int(126 + 54 * strength)
        stream_alpha = int(86 + 54 * strength)

        valve_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(valve_layer)
        leaflet_color = (232, 198, 166, leaflet_alpha)
        leaflet_edge = (255, 238, 208, edge_alpha)
        calcium_color = (246, 238, 210, int(96 + 42 * strength))
        stream_color = (255, 224, 150, stream_alpha)

        def draw_arrow(start, end, width):
            _draw_polyline(draw, [start, end], stream_color, width)
            jx, jy = end[0] - start[0], end[1] - start[1]
            norm = max(0.001, (jx * jx + jy * jy) ** 0.5)
            jx, jy = jx / norm, jy / norm
            head = max(4, int(size * (0.009 + 0.004 * strength)))
            base_pt = (end[0] - jx * head, end[1] - jy * head)
            perp = (-jy, jx)
            draw.polygon(
                [
                    end,
                    (base_pt[0] + perp[0] * head * 0.42, base_pt[1] + perp[1] * head * 0.42),
                    (base_pt[0] - perp[0] * head * 0.42, base_pt[1] - perp[1] * head * 0.42),
                ],
                fill=stream_color,
            )

        def draw_leaflet_pair(horizontal=True):
            if horizontal:
                left_leaflet = [
                    (vcx - vrx * 0.98, vcy - vry * 0.76),
                    (vcx - slit_w / 2, vcy - slit_h * 0.60),
                    (vcx - slit_w / 2, vcy + slit_h * 0.60),
                    (vcx - vrx * 0.98, vcy + vry * 0.76),
                ]
                right_leaflet = [
                    (vcx + vrx * 0.98, vcy - vry * 0.76),
                    (vcx + slit_w / 2, vcy - slit_h * 0.60),
                    (vcx + slit_w / 2, vcy + slit_h * 0.60),
                    (vcx + vrx * 0.98, vcy + vry * 0.76),
                ]
            else:
                left_leaflet = [
                    (vcx - vrx * 0.92, vcy - vry * 0.70),
                    (vcx - slit_w / 2, vcy - slit_h * 0.58),
                    (vcx - slit_w / 2, vcy + slit_h * 0.58),
                    (vcx - vrx * 0.74, vcy + vry * 0.48),
                ]
                right_leaflet = [
                    (vcx + vrx * 0.92, vcy - vry * 0.70),
                    (vcx + slit_w / 2, vcy - slit_h * 0.58),
                    (vcx + slit_w / 2, vcy + slit_h * 0.58),
                    (vcx + vrx * 0.74, vcy + vry * 0.48),
                ]
            for leaflet in (left_leaflet, right_leaflet):
                draw.polygon(leaflet, fill=leaflet_color)
                draw.line(leaflet + [leaflet[0]], fill=leaflet_edge, width=max(1, ring_width - 1))
            draw.line(
                (vcx - slit_w / 2, vcy, vcx + slit_w / 2, vcy),
                fill=(255, 248, 224, int(112 + 40 * strength)),
                width=max(1, ring_width - 1),
            )

        if region_key == "PA":
            neck_len = max(24, int(w * (0.42 + 0.16 * strength)))
            upstream_h = max(12, int(h * (0.58 + 0.12 * strength)))
            throat_h = max(3, int(h * (0.16 - 0.085 * strength)))
            neck_x0 = vcx - vrx * 0.62
            throat_x = vcx + vrx * 0.05
            neck_x1 = vcx + neck_len
            upper = [
                (neck_x0, vcy - upstream_h / 2),
                (throat_x, vcy - throat_h / 2),
                (neck_x1, vcy - max(throat_h * 0.88, 3)),
            ]
            lower = [
                (neck_x0, vcy + upstream_h / 2),
                (throat_x, vcy + throat_h / 2),
                (neck_x1, vcy + max(throat_h * 0.88, 3)),
            ]
            _draw_polyline(draw, upper, leaflet_edge, ring_width)
            _draw_polyline(draw, lower, leaflet_edge, ring_width)
            leaflet_w = max(5, vrx * 0.28)
            draw.polygon(
                [(throat_x - leaflet_w, vcy - upstream_h * 0.28), (throat_x - 1, vcy - throat_h / 2), (throat_x - 1, vcy + throat_h / 2), (throat_x - leaflet_w, vcy + upstream_h * 0.05)],
                fill=leaflet_color,
            )
            draw.polygon(
                [(throat_x + leaflet_w * 0.45, vcy - upstream_h * 0.12), (throat_x + 1, vcy - throat_h / 2), (throat_x + 1, vcy + throat_h / 2), (throat_x + leaflet_w * 0.45, vcy + upstream_h * 0.22)],
                fill=leaflet_color,
            )
            draw.line((throat_x, vcy - throat_h / 2, throat_x, vcy + throat_h / 2), fill=(255, 248, 224, int(120 + 40 * strength)), width=max(1, ring_width - 1))
            draw_arrow((throat_x + 2, vcy), (neck_x1 + vrx * 0.28, vcy - vrx * 0.12), max(1, ring_width - 1))
        else:
            draw_leaflet_pair(horizontal=region_key in {"MV", "TV"})
            if region_key == "AO":
                draw.arc((vcx - vrx, vcy - vry, vcx + vrx, vcy + vry), start=200, end=340, fill=leaflet_edge, width=ring_width)
            else:
                draw.arc((vcx - vrx, vcy - vry, vcx + vrx, vcy + vry), start=170, end=370, fill=leaflet_edge, width=ring_width)
            jx, jy = float(target["jet"][0]), float(target["jet"][1])
            norm = max(0.001, (jx * jx + jy * jy) ** 0.5)
            jx, jy = jx / norm, jy / norm
            jet_len = max(22, int((w + h) * (0.12 + 0.08 * strength)))
            draw_arrow((vcx + jx * vrx * 0.28, vcy + jy * vry * 0.28), (vcx + jx * jet_len, vcy + jy * jet_len), max(1, ring_width - 1))

        if region_key in {"AO", "MV"}:
            calcification_count = {"trace": 0, "mild": 2, "moderate": 4, "severe": 6, "unknown": 3}.get(severity or "unknown", 3)
            for idx in range(calcification_count):
                side = -1 if idx % 2 == 0 else 1
                t = (idx // 2 + 1) / max(1, (calcification_count + 1) // 2)
                px = vcx + side * vrx * (0.28 + 0.38 * t)
                py = vcy + vry * (-0.38 + 0.76 * ((idx * 3) % 7) / 6)
                dot_r = max(1.0, size * (0.0016 + 0.0008 * strength))
                draw.ellipse((px - dot_r, py - dot_r, px + dot_r, py + dot_r), fill=calcium_color)

        overlay = Image.alpha_composite(overlay, valve_layer)
        mode = "mask_local_stenosis_valve"


    elif condition == "regurgitation":
        flow = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(flow)
        alpha = int(72 + 70 * strength)
        line_width = max(2, int(size * (0.004 + 0.004 * strength)))
        if region_key in {"AO", "PA"}:
            start = (x0 + w * 0.72, y0 + h * 0.42)
            end = (x0 + w * 0.28, y0 + h * 0.58)
        elif region_key in {"LV", "LA"}:
            start = (x0 + w * 0.58, y0 + h * 0.72)
            end = (x0 + w * 0.34, y0 + h * 0.32)
        else:
            start = (x0 + w * 0.40, y0 + h * 0.72)
            end = (x0 + w * 0.60, y0 + h * 0.32)
        for offset in (-0.08, 0.0, 0.08):
            points = [
                (start[0] + w * offset, start[1]),
                (cx + w * (offset * 0.45), cy),
                (end[0] - w * offset, end[1]),
            ]
            _draw_polyline(draw, points, (255, 216, 160, alpha), line_width)
        flow_alpha = ImageChops.multiply(flow.getchannel("A"), threshold.filter(ImageFilter.GaussianBlur(max(1, int(size * 0.002)))))
        flow.putalpha(flow_alpha)
        overlay = Image.alpha_composite(overlay, flow)

    elif condition == "pressure_elevation":
        boundary = _mask_boundary(threshold, max(7, int(size * (0.010 + 0.008 * strength)))).filter(ImageFilter.GaussianBlur(max(1, int(size * 0.004))))
        halo_alpha = boundary.point(lambda px: min(px, int(42 + 52 * strength)))
        halo = Image.new("RGBA", base.size, (255, 206, 122, 0))
        halo.putalpha(halo_alpha)
        overlay = Image.alpha_composite(overlay, halo)

    elif condition in {"dysfunction", "hypokinesia"}:
        dim_alpha = threshold.filter(ImageFilter.GaussianBlur(max(1, int(size * 0.003)))).point(lambda px: min(px, int(12 + 20 * strength)))
        dim = Image.new("RGBA", base.size, (38, 38, 42, 0))
        dim.putalpha(dim_alpha)
        overlay = Image.alpha_composite(overlay, dim)
        hatch = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(hatch)
        spacing = max(18, int(size * 0.045))
        line_width = max(1, int(size * 0.0025))
        for x in range(int(x0 - h), int(x1 + h), spacing):
            draw.line((x, y1, x + h, y0), fill=(230, 218, 190, int(34 + 42 * strength)), width=line_width)
        hatch.putalpha(ImageChops.multiply(hatch.getchannel("A"), threshold))
        overlay = Image.alpha_composite(overlay, hatch)

    elif condition == "aneurysm":
        focal = Image.new("L", base.size, 0)
        draw = ImageDraw.Draw(focal)
        fx = x0 + w * (0.66 if region_key in {"AO", "PA"} else 0.56)
        fy = y0 + h * (0.30 if region_key in {"AO", "PA"} else 0.48)
        rx = max(8, w * (0.12 + 0.07 * strength))
        ry = max(8, h * (0.12 + 0.07 * strength))
        draw.ellipse((fx - rx, fy - ry, fx + rx, fy + ry), fill=255)
        focal = ImageChops.multiply(focal.filter(ImageFilter.GaussianBlur(max(2, int(size * 0.004)))), threshold)
        focal_alpha = focal.point(lambda px: min(px, int(34 + 54 * strength)))
        bulge = Image.new("RGBA", base.size, (255, 184, 132, 0))
        bulge.putalpha(focal_alpha)
        overlay = Image.alpha_composite(overlay, bulge)
        edge = _mask_boundary(focal, max(5, int(size * 0.006))).point(lambda px: min(px, int(38 + 52 * strength)))
        line = Image.new("RGBA", base.size, (255, 226, 190, 0))
        line.putalpha(edge)
        overlay = Image.alpha_composite(overlay, line)

    result = Image.alpha_composite(result, overlay)
    return {
        "backend": "local_warp",
        "image_url": save_generated_pil(result),
        "prompt": prompt + f"\n\nLocal effect: deterministic conservative {condition} cue; original anatomy and outer contour are preserved.",
        "negative_prompt": negative_prompt,
        "region": region_key,
        "region_label": region["label"],
        "size": size,
        "mode": mode,
        "condition": condition,
        "severity": severity,
        "warp_offset": [0, 0],
        "warp_config": {"strength": round(strength, 3), "bbox": [x0, y0, x1, y1]},
    }

def generate_with_local_warp(req: ImageGenerateReq, prompt: str, negative_prompt: str, region_key: str, condition: str) -> dict:
    from PIL import Image, ImageChops, ImageFilter

    region = IMAGE_MASK_REGIONS[region_key]
    if not HEART_BASE_PATH.exists():
        raise RuntimeError(f"Missing image asset: {HEART_BASE_PATH.name}")
    mask_path = HEART_MASK_DIR / region["filename"]
    if not mask_path.exists():
        raise RuntimeError(f"Missing mask asset: {region['filename']}")

    size = max(256, min(768, COMFYUI_IMAGE_SIZE))
    size -= size % 8
    base = Image.open(HEART_BASE_PATH).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.open(mask_path).convert("L").resize((size, size), Image.Resampling.LANCZOS)
    threshold = mask.point(lambda px: 255 if px > 12 else 0)
    bbox = threshold.getbbox()
    if not bbox:
        raise RuntimeError(f"Empty mask: {region['filename']}")

    detected_condition, severity = resolve_visual_condition(req.structured or {}, region_key, req.condition)
    config = _local_warp_config(region_key)
    if condition == "hypertrophy" or detected_condition == "hypertrophy":
        return generate_with_local_hypertrophy(req, prompt, negative_prompt, region_key, severity, base, threshold, config)
    if condition == "dilatation" or detected_condition == "dilatation":
        return generate_with_local_dilatation_mesh(req, prompt, negative_prompt, region_key, severity, base, threshold, config)
    if detected_condition in LOCAL_EFFECT_CONDITIONS or condition in LOCAL_EFFECT_CONDITIONS:
        effect_condition = detected_condition if detected_condition in LOCAL_EFFECT_CONDITIONS else condition
        return generate_with_local_condition_effect(req, prompt, negative_prompt, region_key, effect_condition, severity, base, threshold, config)
    if condition == "dilatation" or detected_condition == "dilatation":
        scale = _local_warp_scale(region_key, severity, req.visual_strength)
    elif condition == "hypertrophy" or detected_condition == "hypertrophy":
        scale = 1.16 if req.visual_strength == "clear" else 1.08
    else:
        scale = 1.12 if req.visual_strength == "clear" else 1.06

    x0, y0, x1, y1 = bbox
    pad = max(14, int(size * config["pad"]))
    box = (max(0, x0 - pad), max(0, y0 - pad), min(size, x1 + pad), min(size, y1 + pad))
    crop = base.crop(box)
    crop_mask = threshold.crop(box)
    w, h = crop.size
    scaled_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    enlarged = crop.resize(scaled_size, Image.Resampling.BICUBIC)

    hard_mask = crop_mask.resize(scaled_size, Image.Resampling.NEAREST)
    source_band_width = max(9, int(size * 0.018))
    source_band = ImageChops.subtract(
        crop_mask,
        crop_mask.filter(ImageFilter.MinFilter(_odd_filter_size(source_band_width))),
    )
    source_band = source_band.filter(ImageFilter.MaxFilter(_odd_filter_size(max(3, source_band_width // 3))))
    alpha_mask = source_band.resize(scaled_size, Image.Resampling.NEAREST)
    alpha = enlarged.getchannel("A")
    combined_alpha = ImageChops.multiply(alpha, alpha_mask)
    enlarged.putalpha(combined_alpha)

    center_x = (box[0] + box[2]) / 2
    center_y = (box[1] + box[3]) / 2
    image_center_x = size / 2
    image_center_y = size / 2
    vector_x = center_x - image_center_x
    vector_y = center_y - image_center_y
    override_vector = config.get("offset_vector")
    if override_vector:
        vector_x, vector_y = float(override_vector[0]), float(override_vector[1])
    length = max(1.0, (vector_x ** 2 + vector_y ** 2) ** 0.5)
    outward = max(3, int(size * config["offset"] * (scale - 1.0) / 0.26))
    offset_x = vector_x / length * outward
    offset_y = vector_y / length * outward
    paste_xy = (
        int(center_x + offset_x - scaled_size[0] / 2),
        int(center_y + offset_y - scaled_size[1] / 2),
    )

    result = base.copy()
    placed = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    paste_alpha = Image.new("L", (size, size), 0)
    px, py = paste_xy
    left = max(0, px)
    top = max(0, py)
    right = min(size, px + scaled_size[0])
    bottom = min(size, py + scaled_size[1])
    seam_width = max(3, int(size * 0.004))
    overlap_width = max(5, int(size * 0.007))
    if left < right and top < bottom:
        visible_image = enlarged.crop((left - px, top - py, right - px, bottom - py))
        visible_alpha = alpha_mask.crop((left - px, top - py, right - px, bottom - py))
        placed.alpha_composite(visible_image, (left, top))
        paste_alpha.paste(visible_alpha, (left, top))

        # Preserve the original anatomy. Composite only texture sampled from the
        # original boundary band, expanded into the new outer margin with a tiny
        # overlap so it reads as a continuation instead of a pasted duplicate.
        overlap_zone = threshold.filter(ImageFilter.MaxFilter(_odd_filter_size(overlap_width)))
        protected_core = threshold.filter(ImageFilter.MinFilter(_odd_filter_size(max(3, overlap_width))))
        add_alpha = ImageChops.multiply(paste_alpha, overlap_zone)
        add_alpha = ImageChops.subtract(add_alpha, protected_core)
        add_alpha = add_alpha.point(lambda value: 255 if value > 8 else 0)
        placed.putalpha(ImageChops.multiply(placed.getchannel("A"), add_alpha))
        result = Image.alpha_composite(result, placed)

        seam_mask = ImageChops.subtract(
            add_alpha.filter(ImageFilter.MaxFilter(_odd_filter_size(seam_width))),
            add_alpha.filter(ImageFilter.MinFilter(_odd_filter_size(seam_width))),
        )
        seam_mask = seam_mask.point(lambda value: min(value, 48))
        repaired = result.filter(ImageFilter.SMOOTH)
        repaired.putalpha(seam_mask)
        result = Image.alpha_composite(result, repaired)

    return {
        "backend": "local_warp",
        "image_url": save_generated_pil(result),
        "prompt": prompt + "\n\nLocal warp: deterministic mask-based anatomical enlargement; no diffusion texture synthesis.",
        "negative_prompt": negative_prompt,
        "region": region_key,
        "region_label": region["label"],
        "size": size,
        "mode": "mask_local_warp",
        "condition": detected_condition,
        "warp_scale": round(scale, 3),
        "warp_offset": [round(offset_x, 1), round(offset_y, 1)],
        "warp_config": {"pad": config["pad"], "edge_mode": "boundary_texture_extrusion", "source_band_width": source_band_width, "seam_width": seam_width, "overlap_width": overlap_width, "offset": config["offset"], "offset_vector": config.get("offset_vector")},
    }


def generate_with_webui(req: ImageGenerateReq, prompt: str, negative_prompt: str) -> dict:
    if not IMAGE_API_URL:
        raise RuntimeError("IMAGE_API_URL is not configured")
    payload = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "steps": req.steps,
        "cfg_scale": req.cfg_scale,
        "width": req.width,
        "height": req.height,
        "sampler_name": "DPM++ 2M Karras",
        "batch_size": 1,
        "n_iter": 1,
    }
    r = requests.post(f"{IMAGE_API_URL}/sdapi/v1/txt2img", json=payload, timeout=600)
    if r.status_code != 200:
        raise RuntimeError(r.text)
    data = r.json()
    images = data.get("images") or []
    if not images:
        raise RuntimeError("WebUI returned no images")
    return {
        "backend": "webui",
        "image_url": save_generated_image(images[0]),
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "info": data.get("info"),
    }


def generate_image(req: ImageGenerateReq) -> dict:
    prompt = build_image_prompt(req.structured or {}, req.summary)
    negative_prompt = build_negative_image_prompt()
    backend = IMAGE_BACKEND

    if backend == "webui":
        try:
            return generate_with_webui(req, prompt, negative_prompt)
        except Exception as e:
            return {
                "backend": "webui",
                "image_url": None,
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "error": str(e),
            }

    if backend in {"local_warp", "warp", "local"}:
        region_key = select_mask_region(req.structured or {}, req.region)
        if not region_key:
            return {
                "backend": "local_warp",
                "image_url": None,
                "prompt": "",
                "negative_prompt": negative_prompt,
                "error": "結構化結果中沒有可對應至示意圖的異常部位。",
            }
        prompt, condition = build_masked_image_prompt(req.structured or {}, region_key, req.condition, req.visual_strength)
        try:
            return generate_with_local_warp(req, prompt, negative_prompt, region_key, condition)
        except Exception as e:
            return {
                "backend": "local_warp",
                "image_url": None,
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "region": region_key,
                "region_label": IMAGE_MASK_REGIONS[region_key]["label"],
                "error": str(e),
            }

    if backend == "comfyui":
        region_key = select_mask_region(req.structured or {}, req.region)
        if not region_key:
            return {
                "backend": "comfyui",
                "image_url": None,
                "prompt": "",
                "negative_prompt": negative_prompt,
                "error": "結構化結果中沒有可對應至示意圖的異常部位。",
            }
        prompt, condition = build_masked_image_prompt(req.structured or {}, region_key, req.condition, req.visual_strength)
        try:
            return generate_with_comfyui(req, prompt, negative_prompt, region_key, condition)
        except Exception as e:
            return {
                "backend": "comfyui",
                "image_url": None,
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "region": region_key,
                "region_label": IMAGE_MASK_REGIONS[region_key]["label"],
                "error": str(e),
            }

    return {
        "backend": "mock",
        "image_url": None,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "message": "IMAGE_BACKEND is mock. Set IMAGE_BACKEND=local_warp for deterministic masked deformation or comfyui for diffusion generation.",
    }
