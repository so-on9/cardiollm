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


def _local_warp_scale(severity: str, visual_strength: str) -> float:
    if visual_strength != "clear":
        return 1.12
    return {
        "severe": 1.34,
        "moderate": 1.26,
        "mild": 1.18,
        "trace": 1.10,
        "unknown": 1.22,
    }.get(severity or "unknown", 1.22)


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
    if condition == "dilatation" or detected_condition == "dilatation":
        scale = _local_warp_scale(severity, req.visual_strength)
    elif condition == "hypertrophy" or detected_condition == "hypertrophy":
        scale = 1.16 if req.visual_strength == "clear" else 1.08
    else:
        scale = 1.12 if req.visual_strength == "clear" else 1.06

    x0, y0, x1, y1 = bbox
    pad = max(14, int(size * 0.065))
    box = (max(0, x0 - pad), max(0, y0 - pad), min(size, x1 + pad), min(size, y1 + pad))
    crop = base.crop(box)
    crop_mask = threshold.crop(box)
    w, h = crop.size
    scaled_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    enlarged = crop.resize(scaled_size, Image.Resampling.BICUBIC)

    hard_mask = crop_mask.resize(scaled_size, Image.Resampling.NEAREST)
    feather_radius = max(3, int(size * 0.011))
    feather_mask = hard_mask.filter(ImageFilter.GaussianBlur(feather_radius))
    # Keep the anatomical core opaque; only the outside edge is softened.
    inner_core = hard_mask.filter(ImageFilter.MinFilter(5))
    alpha_mask = ImageChops.lighter(inner_core, feather_mask)
    alpha = enlarged.getchannel("A")
    combined_alpha = ImageChops.multiply(alpha, alpha_mask)
    enlarged.putalpha(combined_alpha)

    result = base.copy()
    center_x = (box[0] + box[2]) / 2
    center_y = (box[1] + box[3]) / 2
    image_center_x = size / 2
    image_center_y = size / 2
    vector_x = center_x - image_center_x
    vector_y = center_y - image_center_y
    length = max(1.0, (vector_x ** 2 + vector_y ** 2) ** 0.5)
    outward = max(3, int(size * 0.026 * (scale - 1.0) / 0.26))
    offset_x = vector_x / length * outward
    offset_y = vector_y / length * outward
    paste_xy = (
        int(center_x + offset_x - scaled_size[0] / 2),
        int(center_y + offset_y - scaled_size[1] / 2),
    )
    _clip_paste_rgba(result, enlarged, paste_xy)

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
