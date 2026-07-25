#!/usr/bin/env python3
"""Multi-phase, maximum-quality OCR for early Hebrew print, with a human gate.

Phase 1 — ENSEMBLE (algorithmic, offline)
    Every text line is read by several algorithms and compared:
      * Tesseract LSTM with the standard `heb` model
      * Tesseract LSTM with the `heb_best` model
      * single-line segmentation (psm 7) on a tight line crop
    Per line we keep each engine's reading + word-confidence, and the
    inter-model agreement (token SequenceMatcher ratio).

Phase 2 — SECOND MODEL (vision)
    The caller (a vision-capable model) reads the same line crops and supplies
    the corrected text. Phase 1 candidates are provided as hints.

Phase 3 — HUMAN GATE
    A line is FLAGGED when it fails Phase 1 — low confidence OR the two models
    disagree. Flagged lines are cropped (upscaled) to PNG so a human can be
    shown the exact image and asked to read it. Nothing is silently guessed.

Design: zero new dependencies (opencv + numpy + pytesseract, already present);
pure functions; deterministic; one page in, one JSON + crops out.
"""
from __future__ import annotations
import sys, os, json, difflib
import cv2
import numpy as np
import pytesseract
from pytesseract import Output

MODELS = ("heb", "heb_best")


def _line_boxes(img, base="heb_best", psm=6):
    """Group Tesseract word boxes into line boxes; return sorted top→bottom."""
    d = pytesseract.image_to_data(img, lang=base, config=f"--oem 1 --psm {psm}",
                                  output_type=Output.DICT)
    lines: dict[tuple, list] = {}
    for i in range(len(d["level"])):
        if d["level"][i] != 5 or int(d["conf"][i]) < 0:
            continue
        if not d["text"][i].strip():
            continue
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        x, y, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
        b = lines.get(key)
        if b is None:
            lines[key] = [x, y, x + w, y + h]
        else:
            b[0] = min(b[0], x); b[1] = min(b[1], y)
            b[2] = max(b[2], x + w); b[3] = max(b[3], y + h)
    return [(v[0], v[1], v[2] - v[0], v[3] - v[1])
            for _, v in sorted(lines.items(), key=lambda kv: kv[1][1])]


def _read_line(crop):
    """Read a single-line crop with each model. Return {model: (text, conf)}."""
    out = {}
    for m in MODELS:
        d = pytesseract.image_to_data(crop, lang=m, config="--oem 1 --psm 7",
                                      output_type=Output.DICT)
        ws = [(d["text"][i], int(d["conf"][i])) for i in range(len(d["text"]))
              if d["text"][i].strip() and int(d["conf"][i]) >= 0]
        text = " ".join(w for w, _ in ws)
        conf = sum(c for _, c in ws) / max(1, len(ws))
        out[m] = (text, conf)
    return out


def analyze_page(img_path, out_dir, conf_thr=65.0, agr_thr=0.80, pad=6):
    img = cv2.imread(img_path)
    if img is None:
        raise SystemExit(f"cannot read {img_path}")
    H, W = img.shape[:2]
    os.makedirs(out_dir, exist_ok=True)
    results, flagged = [], 0
    for idx, (x, y, w, h) in enumerate(_line_boxes(img)):
        if w < 40 or h < 12:               # ignore specks / rules
            continue
        y0, y1 = max(0, y - pad), min(H, y + h + pad)
        x0, x1 = max(0, x - pad), min(W, x + w + pad)
        crop = img[y0:y1, x0:x1]
        rd = _read_line(crop)
        (ta, ca), (tb, cb) = rd["heb"], rd["heb_best"]
        agr = difflib.SequenceMatcher(None, ta.split(), tb.split()).ratio() if (ta or tb) else 0.0
        conf = max(ca, cb)
        candidate = tb if cb >= ca else ta
        flag = (conf < conf_thr) or (agr < agr_thr)
        rec = {"line": idx, "bbox": [int(x), int(y), int(w), int(h)],
               "heb": ta, "heb_best": tb, "conf": round(conf, 1),
               "agreement": round(agr, 2), "candidate": candidate, "flag": bool(flag)}
        if flag:
            p = os.path.join(out_dir, f"line_{idx:02d}.png")
            cv2.imwrite(p, cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
            rec["crop"] = p
            flagged += 1
        results.append(rec)
    with open(os.path.join(out_dir, "lines.json"), "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    return results, flagged


if __name__ == "__main__":
    img_path, out_dir = sys.argv[1], sys.argv[2]
    conf_thr = float(sys.argv[3]) if len(sys.argv) > 3 else 65.0
    agr_thr = float(sys.argv[4]) if len(sys.argv) > 4 else 0.80
    res, flg = analyze_page(img_path, out_dir, conf_thr, agr_thr)
    print(f"lines={len(res)}  flagged={flg}  (rule: conf<{conf_thr} OR agreement<{agr_thr})")
    for r in res:
        mark = "FLAG" if r["flag"] else "  ok"
        print(f"{mark} L{r['line']:02d} conf={r['conf']:5.1f} agr={r['agreement']:.2f} | {r['candidate'][:58]}")
