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
    cfg_scale: float = Field(ge=1.0, le=20.0, default=7.0)

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
        "illegible text, watermark, logo, low quality, blurry, noisy, photorealistic surgery"
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
        "dilatation": "Visibly widen the outer contour of this structure into the allowed masked margin; do not merely change its texture.",
        "hypertrophy": "Visibly thicken the muscular wall while keeping the chamber recognizable.",
        "stenosis": "Visibly narrow the affected anatomical opening while preserving surrounding anatomy.",
        "regurgitation": "Show a restrained backward-flow visual cue confined to this structure.",
        "dysfunction": "Show a restrained abnormal regional appearance without altering surrounding anatomy.",
        "pressure_elevation": "Show restrained visual prominence of this vascular structure.",
    }.get(condition, "Make the abnormality visible while preserving surrounding anatomy.")
    finding = " ".join(word for word in (severity_text, condition_text) if word)
    return (
        "Edit only the permitted anatomical region in the supplied heart cutaway illustration. "
        "Preserve the original illustration style, lighting and all structures outside the edit region. "
        f"In the {region['prompt']}, depict a {strength_text} {finding}. {action_text} "
        "No labels, arrows, text, additional organs or background changes.",
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
        "8": {"class_type": "VAEEncode", "inputs": {"pixels": ["3", 0], "vae": ["1", 2]}},
        "9": {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["8", 0], "mask": ["7g", 0]}},
        "10": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "11": {"class_type": "CLIPTextEncode", "inputs": {"text": negative_prompt, "clip": ["1", 1]}},
        "12": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "seed": secrets.randbits(63), "steps": req.steps, "cfg": req.cfg_scale, "sampler_name": "dpmpp_2m", "scheduler": "karras", "positive": ["10", 0], "negative": ["11", 0], "latent_image": ["9", 0], "denoise": denoise}},
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
        "message": "IMAGE_BACKEND is mock. Set IMAGE_BACKEND=comfyui and IMAGE_API_URL to enable masked generation.",
    }
