# Cardio Draw Figures

這個資料夾保存論文/計畫展示用的心臟繪圖結果。目前展示病變為 `dilatation / enlargement`。

目前分成三個資料夾：

```text
ai_baseline/          舊版 AI baseline，來源為 local_warp_dilatation_test_grid_v4，已修正亂碼標籤
opencv_rule/          OpenCV 規則式渲染 baseline
rejected_ai_drawing/  錯誤 clean-label 嘗試，不可引用
```

---

## ai_baseline

目前 AI baseline 主圖：

```text
ai_baseline/paper_ai_baseline_dilatation_grid_v4_clean_label.png
```

原始亂碼版備份：

```text
ai_baseline/local_warp_dilatation_test_grid_v4_original_mojibake.png
```

來源：

```text
proxy/static/generated/local_warp_dilatation_test_grid_v4.png
```

處理方式：

```text
1. 讀取 local_warp_dilatation_test_grid_v4.png。
2. 切成 3 × 2 六格。
3. 裁掉每格上方亂碼 label band。
4. 保留原圖心臟內容。
5. 重新排成 1080 × 820 px clean-label grid。
```

狀態：

```text
usable as AI baseline / legacy AI-style comparison figure
```

---

## opencv_rule

目前 OpenCV 主圖：

```text
opencv_rule/paper_opencv_dilatation_grid.png
opencv_rule/local_warp_dilatation_true_mask_cv2_ventricle_rim_v8.png
```

已知資訊：

```text
input: heart_base.png + precise anatomical masks from heart_base_mask_true.png
method: OpenCV remap + smooth influence mask + alpha blend
condition: moderate dilatation
single generation size: 768 × 768 px
grid: 1080 × 820 px
regions: AO, PA, LA, RA, LV, RV
LV/RV: outer-rim biased deformation to preserve myocardial texture
status: usable deterministic baseline
```

---


### 2026-06-24 label-spacing cleanup

`opencv_rule/paper_opencv_dilatation_grid.png` 已重新覆寫 label，將 `AOdilatation moderate` 這類黏在一起的文字修成 `AO dilatation moderate`。

備份檔：

```text
opencv_rule/paper_opencv_dilatation_grid_before_label_spacing.png
```

---

## rejected_ai_drawing

此資料夾只保留錯誤/撤回圖檔，避免之後誤用。

```text
rejected_ai_drawing/paper_ai_dilatation_grid_INVALID.png
rejected_ai_drawing/local_warp_dilatation_test_grid_v4_clean_label_INVALID.png
```

撤回原因：

```text
1. 六格幾乎是同一張心臟圖。
2. 沒有保留 local_warp_dilatation_test_grid_v4 原圖的部位差異。
3. 不可作為 AI baseline 或論文圖引用。
```

---

## Main method note

完整方法、參數與論文段落草案請看：

```text
cardiollm/Refer_aidraw/cardio_draw_paper_demo.md
```
