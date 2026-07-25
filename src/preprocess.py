#!/usr/bin/env python3
"""Preprocess a scanned Hebrew page for maximum-quality OCR.

Pipeline (order matters):
  1. load grayscale
  2. estimate & correct skew (project-profile method, robust for text blocks)
  3. remove isolated speckles (connected-component area filter)
  4. optional upscale for small glyphs
  5. clean binarize (Otsu)

Designed for already-bilevel fax/jbig2 scans, where the wins are deskew +
despeckle rather than thresholding. Zero heavy deps: OpenCV + numpy only.
"""
import sys
import cv2
import numpy as np


def deskew(gray):
    # invert so text is white on black for angle search
    inv = cv2.bitwise_not(gray)
    thr = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    best_angle, best_score = 0.0, -1.0
    # search skew by maximizing variance of the horizontal projection profile
    angles = np.arange(-5.0, 5.0 + 1e-9, 0.25)
    h, w = thr.shape
    small = cv2.resize(thr, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    for a in angles:
        M = cv2.getRotationMatrix2D((small.shape[1] / 2, small.shape[0] / 2), a, 1.0)
        rot = cv2.warpAffine(small, M, (small.shape[1], small.shape[0]),
                             flags=cv2.INTER_NEAREST, borderValue=0)
        proj = rot.sum(axis=1, dtype=np.float64)
        score = float(np.var(np.diff(proj)))
        if score > best_score:
            best_score, best_angle = score, a
    M = cv2.getRotationMatrix2D((w / 2, h / 2), best_angle, 1.0)
    out = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC,
                         borderValue=255)
    return out, best_angle


def despeckle(gray, min_area):
    thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    n, lab, stats, _ = cv2.connectedComponentsWithStats(thr, connectivity=8)
    keep = np.zeros_like(thr)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            keep[lab == i] = 255
    # keep = foreground mask; render black text on white
    out = cv2.bitwise_not(keep)
    return out


def main():
    src, dst = sys.argv[1], sys.argv[2]
    scale = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
    min_area = int(sys.argv[4]) if len(sys.argv) > 4 else 6
    gray = cv2.imread(src, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        print("cannot read", src, file=sys.stderr); sys.exit(1)
    gray, ang = deskew(gray)
    clean = despeckle(gray, min_area)
    if scale != 1.0:
        clean = cv2.resize(clean, None, fx=scale, fy=scale,
                           interpolation=cv2.INTER_CUBIC)
        clean = cv2.threshold(clean, 0, 255,
                              cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    # pad a white border (tesseract likes margins)
    clean = cv2.copyMakeBorder(clean, 30, 30, 30, 30,
                               cv2.BORDER_CONSTANT, value=255)
    cv2.imwrite(dst, clean)
    print(f"{src} -> {dst} skew={ang:+.2f} min_area={min_area} scale={scale}")


if __name__ == "__main__":
    main()
