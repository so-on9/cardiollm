# Cardio Draw Paper Demo Method Note

這份文件是給後續協助撰寫論文/計畫書的 AI 或協作者使用。重點是說清楚目前心臟繪圖展示圖的**來源、方法、參數、後處理與論文定位**。

目前論文展示先以 **dilatation / enlargement（心臟腔室與血管擴大）** 作為代表案例，並保留兩組圖：

```text
A. AI baseline 組：local_warp_dilatation_test_grid_v4 原圖修正亂碼標籤
B. OpenCV 組：mask-based rule-guided OpenCV remap v8
```

重要更正：先前錯誤整理出的 `paper_ai_dilatation_grid.png` 六格幾乎是同一張心臟，已移到 `rejected_ai_drawing/`，不可引用。真正要用的 AI baseline 是 `local_warp_dilatation_test_grid_v4.png` 原圖去除亂碼後重新排版的版本。

---

## 1. 展示圖總覽

### Figure A: AI baseline

論文展示主圖：

```text
cardiollm/Refer_aidraw/cardio_draw_figures/ai_baseline/paper_ai_baseline_dilatation_grid_v4_clean_label.png
```

原始亂碼版備份：

```text
cardiollm/Refer_aidraw/cardio_draw_figures/ai_baseline/local_warp_dilatation_test_grid_v4_original_mojibake.png
```

原始 generated 圖：

```text
proxy/static/generated/local_warp_dilatation_test_grid_v4.png
```

這張 clean-label 版只做排版與標籤修正：裁掉原始每格上方亂碼 label，保留原圖心臟內容，再重排成 3 × 2 grid。沒有重新生成心臟內容。

### Figure B: OpenCV rule-guided rendering

論文展示主圖：

```text
cardiollm/Refer_aidraw/cardio_draw_figures/opencv_rule/paper_opencv_dilatation_grid.png
```

同內容備份：

```text
cardiollm/Refer_aidraw/cardio_draw_figures/opencv_rule/local_warp_dilatation_true_mask_cv2_ventricle_rim_v8.png
```

原始 generated 圖：

```text
proxy/static/generated/local_warp_dilatation_true_mask_cv2_ventricle_rim_v8.png
```

### Rejected AI clean-label attempt

錯誤圖保留在：

```text
cardiollm/Refer_aidraw/cardio_draw_figures/rejected_ai_drawing/paper_ai_dilatation_grid_INVALID.png
cardiollm/Refer_aidraw/cardio_draw_figures/rejected_ai_drawing/local_warp_dilatation_test_grid_v4_clean_label_INVALID.png
```

撤回原因：

```text
1. 六格幾乎是同一張心臟圖。
2. 沒有保留 local_warp_dilatation_test_grid_v4 原圖的部位差異。
3. 不可作為 AI baseline 或論文圖引用。
```

---

## 2. 為什麼先展示 dilatation

本階段不先展示全部病變，而是先選擇 dilatation 作為代表性圖例。

原因：

```text
1. 擴大是心臟超音波報告中常見且容易視覺化的結構變化。
2. AO、PA、LA、RA、LV、RV 都能用同一組病變概念比較。
3. 適合展示 AI baseline 與 OpenCV 規則式渲染在視覺可控性上的差異。
4. 以目前完成度、可解釋性與視覺辨識度而言，比 stenosis / hypertrophy 更適合做第一張展示圖。
```

---

## 3. AI baseline 組方法

### 3.1 方法定位

AI baseline 組使用：

```text
legacy AI / inpaint-style dilatation baseline from local_warp_dilatation_test_grid_v4
```

中文可寫成：

```text
舊版 AI 繪圖/局部編修流程產生之心臟擴大 baseline
```

本組目前作為 baseline，而不是最終最佳模型成果。它的價值在於：這是原先討論與比較使用的 AI 繪圖版本，已經能粗略呈現不同部位擴大，但標籤亂碼需要修正。

### 3.2 圖檔來源

AI baseline 來源：

```text
source image: proxy/static/generated/local_warp_dilatation_test_grid_v4.png
source size: 768 × 568 px
layout: 3 columns × 2 rows
regions: AO, PA, LA, RA, LV, RV
issue: original top labels contain mojibake / encoding artifacts
```

clean-label 輸出：

```text
output image: cardiollm/Refer_aidraw/cardio_draw_figures/ai_baseline/paper_ai_baseline_dilatation_grid_v4_clean_label.png
output size: 1080 × 820 px
layout: 3 columns × 2 rows
labels: AO / PA / LA / RA / LV / RV dilatation
subtitle: AI baseline / v4
```

### 3.3 後處理方式

clean-label 版處理流程：

```text
1. 讀取 local_warp_dilatation_test_grid_v4.png。
2. 將原圖切成 3 × 2 六個 cell。
3. 每個 cell 裁掉上方約 22 px 亂碼 label band。
4. 保留原圖中的心臟內容與部位變化。
5. 將六格重新排成 1080 × 820 px grid。
6. 加上乾淨英文 label。
7. 輸出 paper_ai_baseline_dilatation_grid_v4_clean_label.png。
```

這一步是 presentation cleanup，不是重新生成，不改動原圖中的病灶視覺內容。

### 3.4 模型與可重現性說明

目前專案中的 AI inpaint 候選 checkpoint 為：

```text
model file: 512-inpainting-ema.safetensors
local model path: /home/ct/comfyui/ComfyUI/models/checkpoints/512-inpainting-ema.safetensors
model family: Stable Diffusion inpainting checkpoint
```

目前 `.env` 中可確認：

```text
IMAGE_BACKEND=local_warp
COMFYUI_CHECKPOINT=512-inpainting-ema.safetensors
COMFYUI_IMAGE_SIZE=512
COMFYUI_DENOISE=0.42
```

注意：網站目前預設 backend 是 `local_warp`，不是 ComfyUI。`local_warp_dilatation_test_grid_v4.png` 是舊版展示圖，保留作為 AI baseline / legacy baseline。其 exact seed、workflow JSON、完整 prompt log 未完整封存，因此論文中不應宣稱它是 fully reproducible locked experiment。

如果未來要重跑嚴格 AI 實驗，必須保存：

```text
checkpoint name
checkpoint hash
workflow JSON
prompt / negative prompt
seed
steps / cfg / sampler / scheduler / denoise
base image version
mask file version
accepted output images
manual review result
```

---

## 4. OpenCV 規則式組方法

### 4.1 方法定位

OpenCV 組的定位是：

```text
mask-based rule-guided anatomical rendering
```

中文：

```text
基於遮罩與規則引導的心臟解剖視覺化
```

這組不使用生成式模型，而是根據部位 mask 與幾何規則對原圖做可控變形。

### 4.2 使用的演算法

核心演算法：

```text
OpenCV remap + smooth influence mask + alpha blending
```

主要流程：

```text
1. 讀取 heart_base.png。
2. 讀取指定解剖部位 mask。
3. 將底圖與 mask resize 到 768 × 768。
4. 依 mask bbox 建立 ROI。
5. 對 mask 做 dilation + Gaussian blur 形成 influence map。
6. 使用 cv2.remap 做局部 outward deformation。
7. 使用 alpha blend 與原圖融合。
8. 輸出單張結果。
9. 將六個部位排成 3 × 2 grid。
```

概念式流程：

```text
mask_binary = threshold(mask)
mask_dilated = dilate(mask_binary, elliptical_kernel)
influence = gaussian_blur(mask_dilated)
influence = normalize(influence, 0.0, 1.0)

local_scale = 1.0 + (scale - 1.0) * influence
map_x = center_x + (x - center_x) / local_scale
map_y = center_y + (y - center_y) / local_scale

warped_roi = cv2.remap(roi, map_x, map_y, interpolation=cv2.INTER_CUBIC)
result = alpha_blend(original_roi, warped_roi, influence)
```

### 4.3 使用的 mask

OpenCV v8 使用的是較精準的 true mask：

```text
heart_base_mask_true.png 拆出的 masks/
```

包含：

```text
aorta.png
pulmonary_artery.png
left_atrium.png
right_atrium.png
left_ventricle.png
right_ventricle.png
```

### 4.4 OpenCV v8 全域參數

```text
output grid: 1080 × 820 px
single generation size: 768 × 768 px
layout: 3 columns × 2 rows
cell size: 360 × 410 px
thumbnail size: 320 × 320 px
backend: local_warp / OpenCV remap
condition: dilatation
severity: moderate
visual_strength: clear
base resize: 768 × 768
mask threshold: > 12 → 255
interpolation: cv2.INTER_CUBIC
border mode: cv2.BORDER_REFLECT_101
blend: smooth alpha blend from influence map
```

Influence map 參數：

```text
dilate_px = max(5, int(size * 0.014)) = 10 when size = 768
blur_px = max(11, int(size * 0.022)) = 17 when size = 768
kernel = cv2.MORPH_ELLIPSE
pad = max(36, int(size * (region_pad + 0.070)))
```

### 4.5 OpenCV v8 per-region parameters

| Region | Base scale | Effective scale | Pad px | Notes |
|---|---:|---:|---:|---|
| AO | 1.15 | 1.15 | 92 | regular vessel/chamber remap |
| PA | 1.15 | 1.15 | 93 | cleaned PA mask, no left fragment |
| LA | 1.23 | 1.23 | 99 | regular chamber remap |
| RA | 1.26 | 1.26 | 103 | regular chamber remap |
| LV | 1.23 | 1.133 | 99 | ventricle outer-rim preservation |
| RV | 1.14 | 1.081 | 89 | ventricle outer-rim preservation |

### 4.6 LV/RV special handling

LV/RV 不能像心房一樣整個 mask 大幅拉動，否則會吃掉內部心肌紋理。因此 v8 對心室使用 outer-rim biased deformation。

```text
effective_scale = 1.0 + (scale - 1.0) * 0.58
inner_px = max(5, int(size * 0.014))
vent_blur = max(21, int(size * 0.034))
warp_influence = max(outer_f * 0.95, edge_f * 0.28)
blend_influence = max(outer_f * 0.88, edge_f * 0.24)
```

---

## 5. PowerPaint v2-1 與其他 inpaint 模型不作主圖的原因

PowerPaint v2-1 已成功安裝並可產圖，但目前不作為本展示主圖。原因不是不能跑，而是生成行為不符合精細解剖示意任務。

已確認：

```text
PowerPaint v2-1 checkpoint downloaded
conda env: ppt
Python: 3.9
GPU: RTX 5070 Ti
Torch: 2.8.0+cu128
CUDA available: yes
```

不採用原因：

```text
1. PowerPaint 較傾向把 mask 區域視為要重建 / 插入的新物件。
2. 本任務需要保留原本心臟插圖，只讓指定解剖部位擴大。
3. PowerPaint 容易大幅重畫 mask 內的解剖紋理、邊界與鄰近構造。
4. 對 dilatation 這種幾何變化而言，模型有時會生成新形狀，而不是單純擴大原結構。
5. 對論文主圖而言，可控性與可解釋性不足。
```

論文中可寫成：

```text
Although PowerPaint v2-1 was tested as a diffusion-based inpainting candidate, its outputs showed excessive local rewriting for fine-grained cardiac anatomy. Therefore, it was retained as an exploratory negative candidate rather than the primary visualization method.
```

---

## 6. 方法學定論

AI baseline 與 OpenCV 組各自定位不同。

AI baseline 的價值：

```text
1. 可作為生成式 / AI-style 心臟繪圖流程的 baseline。
2. 能展示早期 AI 編修結果對各部位擴大的粗略視覺化能力。
3. 適合作為 OpenCV 規則式方法的比較對象。
```

AI baseline 的限制：

```text
1. exact seed / workflow metadata 未完整封存。
2. 解剖一致性與可控性不如 OpenCV。
3. 不應宣稱為臨床準確圖像或 fully reproducible experiment。
```

OpenCV 組的價值：

```text
1. deterministic，同一輸入與參數會得到同一輸出。
2. 可解釋，每個部位如何變形可由 mask 與 scale 描述。
3. 較不容易生成不存在的解剖構造。
4. 適合作為目前可控 baseline 與部署備援。
```

最後定論：

```text
The legacy AI baseline provides an early AI-style visualization reference after correcting label encoding artifacts, while the OpenCV-based rendering provides a deterministic and interpretable rule-guided baseline. The AI baseline is useful for comparison, but the OpenCV pipeline is currently more controllable and reproducible.
```

中文定論：

```text
舊版 AI baseline 可作為早期 AI-style 心臟擴大視覺化參考；OpenCV 規則式方法則提供更可控、可重現且可解釋的 baseline。論文中可比較兩者，但不可把 AI baseline 說成臨床診斷模型或完整可重現的嚴格實驗。
```

---

## 7. 建議論文寫法

### 中文段落草案

```text
本研究以心臟結構擴大作為視覺化模組的代表性案例，並比較兩種心臟示意圖生成策略。第一種為舊版 AI baseline，其來源為 local_warp_dilatation_test_grid_v4，經由去除原始亂碼標籤並重新排版後作為 AI-style 視覺化 baseline；第二種為基於解剖遮罩與 OpenCV 幾何變形的規則式渲染流程。AI baseline 可呈現早期 AI 編修流程對心臟擴大的視覺化結果，但其生成參數與可重現性紀錄較不完整。OpenCV 組則透過預先標註的解剖遮罩與可控的局部變形規則，提供較穩定且可解釋的 deterministic baseline。
```

### English draft

```text
Cardiac chamber and vessel dilatation was selected as the representative use case for the visualization module. Two visualization strategies were compared. The first was a legacy AI baseline derived from local_warp_dilatation_test_grid_v4, with encoding artifacts removed and clean labels reconstructed for presentation. The second was a rule-guided OpenCV rendering pipeline based on anatomical masks and controlled geometric deformation. The AI baseline provides an early AI-style visualization reference, whereas the OpenCV-based approach offers a more controllable and interpretable deterministic baseline.
```

---

## 8. Figure captions

### Figure A: AI baseline

```text
Figure A. Legacy AI baseline visualization of representative cardiac dilatation findings. The figure was reconstructed from local_warp_dilatation_test_grid_v4 by removing the original mojibake labels and rebuilding a clean 3 × 2 grid. The underlying heart images were not regenerated during this presentation cleanup.
```

中文：

```text
圖 A. 舊版 AI baseline 之心臟結構擴大示意圖。此圖由 local_warp_dilatation_test_grid_v4 移除原始亂碼標籤後重新排版為 3 × 2 clean-label grid；重新排版過程未重新生成心臟圖像內容。
```

### Figure B: OpenCV rendering

```text
Figure B. Rule-guided OpenCV rendering of representative cardiac dilatation findings. Anatomical masks were used to define target regions, followed by local remapping and alpha blending to produce controlled deformation.
```

中文：

```text
圖 B. 使用解剖遮罩與 OpenCV 規則式局部變形產生之心臟結構擴大示意圖。此方法透過局部 remap 與透明度融合控制解剖部位擴張。
```

---

## 9. 給其他 AI 的注意事項

```text
1. AI baseline 主圖是 ai_baseline/paper_ai_baseline_dilatation_grid_v4_clean_label.png。
2. AI baseline 來源是 proxy/static/generated/local_warp_dilatation_test_grid_v4.png。
3. clean-label 版只修正亂碼標籤與排版，不是重新生成。
4. rejected_ai_drawing/ 裡的 INVALID 圖不可引用。
5. OpenCV 組是 deterministic OpenCV remap + anatomical masks。
6. PowerPaint v2-1 是探索過但目前不採用為主圖。
7. 不要宣稱任何圖可作臨床診斷；它們是 anatomical illustration / visual explanation。
8. 不要宣稱 AI baseline 是 fully reproducible locked experiment；exact seed / workflow metadata 未完整封存。
```

---

## 10. 圖檔清單

### AI baseline group

```text
cardiollm/Refer_aidraw/cardio_draw_figures/ai_baseline/paper_ai_baseline_dilatation_grid_v4_clean_label.png
cardiollm/Refer_aidraw/cardio_draw_figures/ai_baseline/local_warp_dilatation_test_grid_v4_original_mojibake.png
```

### OpenCV rule-guided group

```text
cardiollm/Refer_aidraw/cardio_draw_figures/opencv_rule/paper_opencv_dilatation_grid.png
cardiollm/Refer_aidraw/cardio_draw_figures/opencv_rule/local_warp_dilatation_true_mask_cv2_ventricle_rim_v8.png
```

### Rejected files

```text
cardiollm/Refer_aidraw/cardio_draw_figures/rejected_ai_drawing/paper_ai_dilatation_grid_INVALID.png
cardiollm/Refer_aidraw/cardio_draw_figures/rejected_ai_drawing/local_warp_dilatation_test_grid_v4_clean_label_INVALID.png
```
