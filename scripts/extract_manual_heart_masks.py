#!/usr/bin/env python3
"""Extract anatomical masks from a manually color-overlaid heart preview."""

from collections import defaultdict
from pathlib import Path
from math import sqrt

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "proxy" / "static" / "assets"
BASE_PATH = ASSETS / "heart_base.png"
PREVIEW_PATH = ASSETS / "heart_masks_manual_preview.png"
OUT_DIR = ASSETS / "masks_manual"
VALIDATION_PATH = ASSETS / "heart_masks_manual_extracted_preview.png"
INPAINT_DIR = ASSETS / "inpaint"
INPAINT_MASK_DIR = INPAINT_DIR / "masks"
INPAINT_PADDING = 160

REGIONS = {
    "aorta": (255, 0, 0),
    "pulmonary_artery": (0, 191, 255),
    "left_atrium": (255, 208, 0),
    "left_ventricle": (255, 61, 141),
    "right_atrium": (0, 208, 132),
    "right_ventricle": (36, 107, 255),
    "mitral_valve": (182, 92, 255),
    "tricuspid_valve": (255, 240, 0),
    "superior_vena_cava": (0, 255, 255),
    "inferior_vena_cava": (255, 122, 0),
}

MIN_DELTA_SQ = 9
MIN_ALPHA = 0.025
MAX_ERROR_SQ = 2.5 * 2.5


def fit_overlay(base, preview, color):
    delta = tuple(preview[i] - base[i] for i in range(3))
    vector = tuple(color[i] - base[i] for i in range(3))
    denominator = sum(channel * channel for channel in vector)
    if denominator < 1:
        return None
    alpha = sum(delta[i] * vector[i] for i in range(3)) / denominator
    alpha = min(1.0, max(0.0, alpha))
    error_sq = sum(
        (preview[i] - (base[i] + alpha * vector[i])) ** 2 for i in range(3)
    )
    return error_sq, alpha


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def keep_largest_component(image):
    bbox = image.getbbox()
    if bbox is None:
        return image, 0

    crop = image.crop(bbox)
    width, height = crop.size
    values = bytearray(crop.tobytes())
    best = []

    for start in range(len(values)):
        if not values[start]:
            continue
        values[start] = 0
        component = [start]
        stack = [start]
        while stack:
            index = stack.pop()
            x = index % width
            neighbors = []
            if x:
                neighbors.append(index - 1)
            if x + 1 < width:
                neighbors.append(index + 1)
            if index >= width:
                neighbors.append(index - width)
            if index + width < len(values):
                neighbors.append(index + width)
            for neighbor in neighbors:
                if values[neighbor]:
                    values[neighbor] = 0
                    component.append(neighbor)
                    stack.append(neighbor)
        if len(component) > len(best):
            best = component

    kept = Image.new("L", image.size, 0)
    source = crop.load()
    output = kept.load()
    left, top = bbox[:2]
    for index in best:
        x = index % width
        y = index // width
        output[left + x, top + y] = source[x, y]
    return kept, len(best)


def extract_masks(base, preview):
    width, height = base.size
    base_pixels = base.load()
    preview_pixels = preview.load()
    values = {name: Image.new("L", base.size, 0) for name in REGIONS}
    mask_pixels = {name: image.load() for name, image in values.items()}
    accepted_alpha = defaultdict(list)

    bbox = base.getbbox() or (0, 0, width, height)
    for y in range(bbox[1], bbox[3]):
        for x in range(bbox[0], bbox[2]):
            base_rgb = base_pixels[x, y][:3]
            preview_rgb = preview_pixels[x, y][:3]
            delta_sq = sum((preview_rgb[i] - base_rgb[i]) ** 2 for i in range(3))
            if delta_sq < MIN_DELTA_SQ:
                continue

            best = None
            for name, color in REGIONS.items():
                fitted = fit_overlay(base_rgb, preview_rgb, color)
                if fitted is None:
                    continue
                error_sq, alpha = fitted
                if best is None or error_sq < best[0]:
                    best = error_sq, alpha, name

            if best is None:
                continue
            error_sq, alpha, name = best
            if error_sq <= MAX_ERROR_SQ and alpha >= MIN_ALPHA:
                mask_pixels[name][x, y] = round(alpha * 255)
                accepted_alpha[name].append(alpha)

    for name, image in values.items():
        image, component_size = keep_largest_component(image)
        alphas = [value / 255 for value in image.getdata() if value]
        if not alphas:
            raise RuntimeError(f"No overlay pixels detected for {name}")
        core_alpha = percentile(alphas, 0.80)
        scale = 255 / max(core_alpha * 255, 1)
        values[name] = image.point(lambda value, s=scale: min(255, round(value * s)))
        print(f"{name}: retained {component_size} connected pixels")

    return values


def render_validation(base, masks):
    rendered = base.copy()
    for name, color in REGIONS.items():
        mask = masks[name].point(lambda value: round(value * 0.48))
        overlay = Image.new("RGBA", base.size, (*color, 0))
        overlay.putalpha(mask)
        rendered = Image.alpha_composite(rendered, overlay)
    return rendered


def write_inpaint_assets(base, masks):
    size = (base.width + INPAINT_PADDING * 2, base.height + INPAINT_PADDING * 2)
    offset = (INPAINT_PADDING, INPAINT_PADDING)
    INPAINT_MASK_DIR.mkdir(parents=True, exist_ok=True)
    padded_base = Image.new("RGBA", size, (0, 0, 0, 0))
    padded_base.paste(base, offset)
    padded_base.save(INPAINT_DIR / "heart_base.png")
    for name, mask in masks.items():
        padded_mask = Image.new("L", size, 0)
        padded_mask.paste(mask, offset)
        padded_mask.save(INPAINT_MASK_DIR / f"{name}.png")
    print(f"Inpainting assets: {INPAINT_DIR} ({size[0]} x {size[1]})")


def main():
    base = Image.open(BASE_PATH).convert("RGBA")
    preview = Image.open(PREVIEW_PATH).convert("RGBA")
    if preview.size != base.size:
        raise ValueError(f"Preview size {preview.size} does not match base size {base.size}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    masks = extract_masks(base, preview)
    for name, mask in masks.items():
        path = OUT_DIR / f"{name}.png"
        mask.save(path)
        print(f"{name}: {mask.getbbox()} -> {path.name}")

    render_validation(base, masks).save(VALIDATION_PATH)
    print(f"Validation preview: {VALIDATION_PATH}")
    write_inpaint_assets(base, masks)


if __name__ == "__main__":
    main()
