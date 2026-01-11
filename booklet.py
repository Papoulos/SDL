#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
booklet.py

Génère un livret (booklet) prêt à l'impression (mode pliure).
Ajouts récents :
 - compensation du "creep" (--creep en mm par feuille physique)
 - mode test (--test) et grille mm (--test-grid) pour calibration

Usage:
    python booklet.py input.pdf [output.pdf] [--options]
    python booklet.py --test [output.pdf] [--test-grid] [--options]

Options:
    --sheets N          feuilles par carnet (1 feuille = 4 pages). Default 4
    --paper A4|Letter   papier cible. Default A4
    --gutter MM         gutter en mm (pliure). Default 0
    --overlap-mm MM     micro-chevauchement central en mm. Default 0.2
    --pad blank|last    padding du dernier carnet. Default blank
    --scale-mode fit|fill
    --creep MM          compensation creep en mm par feuille physique (0 = désactivé)
    --test              génère un PDF test et l'utilise comme source
    --test-pages N      pages du PDF test (default 20)
    --test-grid         ajoute un quadrillage 1 mm sur le PDF test + graduations 10 mm
    --debug-rects       dessine rectangles cible/placé (debug)
    --verbose           logs verboses
"""
from pathlib import Path
import argparse
import sys
import tempfile
import os
import math
import json
import requests

try:
    import fitz  # PyMuPDF
except Exception:
    print("PyMuPDF requis. Installer: pip install pymupdf")
    raise

# Conversion mm -> points
MM_TO_PT = 72.0 / 25.4
def mm_to_pt(mm: float) -> float:
    return mm * MM_TO_PT

# Papier portrait (points)
A4_WIDTH_PT = 595.276
A4_HEIGHT_PT = 841.89
A5_WIDTH_MM = 148.0
A5_HEIGHT_MM = 210.0
LETTER_WIDTH_PT = 612.0
LETTER_HEIGHT_PT = 792.0

# ---------------- utilitaires ----------------

def smallest_multiple_of_4_ge(n: int) -> int:
    if n <= 0:
        return 0
    return ((n + 3) // 4) * 4

def make_blank_page(width_pt, height_pt):
    tmp = fitz.open()
    tmp.new_page(width=width_pt, height=height_pt)
    return tmp

# ---------------- géométrie / scaling ----------------

def compute_embed_rects(page_width: float, page_height: float, gutter_pt: float, margin_tlbr, overlap_pt: float = 0.0):
    top, leftm, bottom, rightm = margin_tlbr
    inner_width = page_width - leftm - rightm
    inner_height = page_height - top - bottom

    half_w = inner_width / 2.0

    if gutter_pt == 0:
        left_x0 = leftm
        left_x1 = leftm + half_w + (overlap_pt / 2.0)
        right_x0 = leftm + half_w - (overlap_pt / 2.0)
        right_x1 = leftm + 2 * half_w
        y0 = top
        y1 = top + inner_height
        rect_left = fitz.Rect(left_x0, y0, left_x1, y1)
        rect_right = fitz.Rect(right_x0, y0, right_x1, y1)
        return rect_left, rect_right

    offset = gutter_pt / 2.0
    left_x0 = leftm - offset
    left_x1 = leftm + half_w - offset
    right_x0 = leftm + half_w + offset
    right_x1 = leftm + 2 * half_w + offset

    if overlap_pt > 0:
        left_x1 += overlap_pt / 2.0
        right_x0 -= overlap_pt / 2.0

    y0 = top
    y1 = top + inner_height
    rect_left = fitz.Rect(left_x0, y0, left_x1, y1)
    rect_right = fitz.Rect(right_x0, y0, right_x1, y1)
    return rect_left, rect_right

def fit_src_rect_into_target(target_rect: fitz.Rect, src_rect: fitz.Rect, scale_mode: str = "fit"):
    target_w = target_rect.width
    target_h = target_rect.height
    src_w = src_rect.width
    src_h = src_rect.height

    if src_w <= 0 or src_h <= 0:
        return target_rect

    if scale_mode == "fill":
        new_w = target_w
        new_h = target_h
    else:
        scale = min(target_w / src_w, target_h / src_h)
        new_w = src_w * scale
        new_h = src_h * scale

    x0 = target_rect.x0 + (target_w - new_w) / 2.0
    y0 = target_rect.y0 + (target_h - new_h) / 2.0
    x1 = x0 + new_w
    y1 = y0 + new_h
    return fitz.Rect(x0, y0, x1, y1)

# ---------------- imposition ----------------

def split_into_booklets_minimize_last(pages, signature, blank_doc, pad_mode="blank"):
    out = []
    total = len(pages)
    idx = 0
    while idx + signature <= total:
        out.append(pages[idx:idx + signature])
        idx += signature

    rem = total - idx
    if rem > 0:
        last_sig = smallest_multiple_of_4_ge(rem)
        chunk = pages[idx: idx + rem]
        if pad_mode == "blank":
            for _ in range(last_sig - rem):
                chunk.append((blank_doc, 0))
        elif pad_mode == "last":
            last = chunk[-1]
            for _ in range(last_sig - rem):
                chunk.append(last)
        else:
            for _ in range(last_sig - rem):
                chunk.append((blank_doc, 0))
        out.append(chunk)
    return out

def place_page_scaled_center(dest_page, src_doc, src_pno, target_rect):
    src_page = src_doc[src_pno]
    src_rect = src_page.rect
    scale = min(target_rect.width / src_rect.width, target_rect.height / src_rect.height)
    new_w = src_rect.width * scale
    new_h = src_rect.height * scale
    x = target_rect.x0 + (target_rect.width - new_w) / 2
    y = target_rect.y0 + (target_rect.height - new_h) / 2
    dest_page.show_pdf_page(fitz.Rect(x, y, x + new_w, y + new_h), src_doc, src_pno)

def imposation_for_signature(signature):
    if signature % 4 != 0:
        raise ValueError("signature must be multiple of 4")
    N = signature
    sheets = []
    sheets_count = N // 4
    for i in range(sheets_count):
        left_recto = N - 2 * i
        right_recto = 1 + 2 * i
        left_verso = 2 + 2 * i
        right_verso = N - 1 - 2 * i
        sheets.append((left_recto, right_recto, left_verso, right_verso))
    return sheets

# ---------------- création du booklet ----------------

def create_booklet_pdf(input_path, output_path, paper="A4", signature=16, gutter_mm=0.0,
                       creep_mm: float = 0.0,
                       book: bool = False,
                       verbose=False):
    in_doc = fitz.open(input_path)
    if in_doc.needs_pass:
        raise RuntimeError("Le PDF d'entrée est protégé / chiffré. Impossible de continuer.")

    if paper.upper() == "A4":
        portrait_w = A4_WIDTH_PT
        portrait_h = A4_HEIGHT_PT
    elif paper.upper() in ("LETTER", "USLETTER", "LETTER-8.5X11"):
        portrait_w = LETTER_WIDTH_PT
        portrait_h = LETTER_HEIGHT_PT
    else:
        raise ValueError("Paper A4 ou Letter seulement supporté.")

    landscape_w = portrait_h
    landscape_h = portrait_w

    if verbose:
        print(f"[+] Input pages: {len(in_doc)}")
        print(f"[+] Target paper: {paper} (landscape {landscape_w:.1f} x {landscape_h:.1f} pts)")

    pages = [(in_doc, pno) for pno in range(len(in_doc))]
    blank_doc = make_blank_page(portrait_w, portrait_h)

    if book:
        if len(pages) >= 2:

            # Supprimer la première et la dernière page
            pages.pop(0)
            pages.pop(-1)
            if verbose:
                print(f"[+] Suppression de la première et de la dernière page (mode --book).")
        elif verbose:
            print(f"[!] Pas assez de pages pour supprimer la couverture et le dos (mode --book).")

        blank_page_entry = (blank_doc, 0)
        # 2 pages au début
        pages.insert(0, blank_page_entry)
        pages.insert(0, blank_page_entry)
        # 2 pages à la fin
        pages.append(blank_page_entry)
        pages.append(blank_page_entry)
        if verbose:
            print(f"[+] Ajout de 2+2 pages blanches pour la reliure (mode --book). Nouveau total : {len(pages)} pages.")

    pad_mode = "blank"
    scale_mode = "fill"
    overlap_mm = 0.2
    booklets = split_into_booklets_minimize_last(pages, signature, blank_doc, pad_mode=pad_mode)
    if verbose:
        print(f"[+] Booklets à générer: {len(booklets)} sizes: {[len(b) for b in booklets]}")

    out_doc = fitz.open()
    gutter_pt = mm_to_pt(gutter_mm)
    overlap_pt = mm_to_pt(overlap_mm)
    creep_per_sheet_pt = mm_to_pt(creep_mm)

    # margins default 0
    margin_mm = 0.0
    margin_pts = (mm_to_pt(margin_mm), mm_to_pt(margin_mm), mm_to_pt(margin_mm), mm_to_pt(margin_mm))

    if verbose and len(pages) > 0:
        try:
            sample_doc, sample_pno = pages[0]
            sample_rect = sample_doc[sample_pno].rect
            print(f"[DEBUG] sample source rect: {sample_rect} (w={sample_rect.width:.2f} h={sample_rect.height:.2f})")
        except Exception:
            pass

    booklet_idx = 0
    for booklet in booklets:
        booklet_idx += 1
        sig_here = len(booklet)
        if verbose:
            print(f"[+] Processing booklet {booklet_idx}/{len(booklets)} (signature={sig_here})")

        sheets_pattern = imposation_for_signature(sig_here)
        sheets_count = sig_here // 4

        for sheet_idx, sheet in enumerate(sheets_pattern):
            lr, rr, lv, rv = sheet
            lr_i = lr - 1
            rr_i = rr - 1
            lv_i = lv - 1
            rv_i = rv - 1

            rect_left, rect_right = compute_embed_rects(landscape_w, landscape_h, gutter_pt, margin_pts, overlap_pt=overlap_pt)

            # apply creep compensation if enabled
            if creep_per_sheet_pt > 0 and sheets_count > 0:
                creep_for_sheet = creep_per_sheet_pt * max(0, (sheets_count - 1 - sheet_idx))
                shift_each_side = creep_for_sheet / 2.0
                rect_left = fitz.Rect(rect_left.x0 + shift_each_side, rect_left.y0, rect_left.x1 + shift_each_side, rect_left.y1)
                rect_right = fitz.Rect(rect_right.x0 - shift_each_side, rect_right.y0, rect_right.x1 - shift_each_side, rect_right.y1)
                if verbose:
                    print(f"[DEBUG] sheet_idx={sheet_idx} creep_for_sheet_pt={creep_for_sheet:.3f} shift_each_side={shift_each_side:.3f}")

            if verbose:
                print(f"[DEBUG] rect_left: {rect_left}")
                print(f"[DEBUG] rect_right: {rect_right} (gutter_mm={gutter_mm} overlap_mm={overlap_mm} creep_mm={creep_mm})")

            # Recto
            page_recto = out_doc.new_page(width=landscape_w, height=landscape_h)

            # left recto
            sdoc, spno = booklet[lr_i]
            try:
                src_rect = sdoc[spno].rect
                target_rect = rect_left
                placed_rect = fit_src_rect_into_target(target_rect, src_rect, scale_mode=scale_mode)
                page_recto.show_pdf_page(placed_rect, sdoc, spno)
            except Exception as e:
                if verbose:
                    print(f"[!] Warning inserting recto-left: {e}")

            # right recto
            sdoc, spno = booklet[rr_i]
            try:
                src_rect = sdoc[spno].rect
                target_rect = rect_right
                placed_rect = fit_src_rect_into_target(target_rect, src_rect, scale_mode=scale_mode)
                page_recto.show_pdf_page(placed_rect, sdoc, spno)
            except Exception as e:
                if verbose:
                    print(f"[!] Warning inserting recto-right: {e}")

            # Verso
            page_verso = out_doc.new_page(width=landscape_w, height=landscape_h)

            sdoc, spno = booklet[lv_i]
            try:
                src_rect = sdoc[spno].rect
                target_rect = rect_left
                placed_rect = fit_src_rect_into_target(target_rect, src_rect, scale_mode=scale_mode)
                page_verso.show_pdf_page(placed_rect, sdoc, spno)
            except Exception as e:
                if verbose:
                    print(f"[!] Warning inserting verso-left: {e}")

            sdoc, spno = booklet[rv_i]
            try:
                src_rect = sdoc[spno].rect
                target_rect = rect_right
                placed_rect = fit_src_rect_into_target(target_rect, src_rect, scale_mode=scale_mode)
                page_verso.show_pdf_page(placed_rect, sdoc, spno)
            except Exception as e:
                if verbose:
                    print(f"[!] Warning inserting verso-right: {e}")

    out_doc.save(output_path)
    out_doc.close()
    in_doc.close()
    blank_doc.close()
    if verbose:
        print(f"[+] Booklet saved to: {output_path}")

# ---------------- CLI ----------------

def parse_args():
    parser = argparse.ArgumentParser(description="Générer un livret (booklet) prêt à imprimer.")
    parser.add_argument("input", nargs="?", help="PDF d'entrée (source A4 attendu). Si --test utilisé, peut être omis.")
    parser.add_argument("output", nargs="?", help="PDF de sortie (optionnel). Si absent -> '<input_stem> - Booklet.pdf' or 'Test - Booklet.pdf' for --test")
    parser.add_argument("--sheets", type=int, default=4, help="Feuilles par carnet (1 feuille = 4 pages). Default 4")
    parser.add_argument("--book", action="store_true", help="Ajoute deux pages blanches recto verso au début et à la fin pour la reliure.")
    parser.add_argument("--paper", type=str, default="A4", help="Paper target (A4 or Letter). Default A4")
    parser.add_argument("--gutter", type=float, default=0.0, help="Gutter (pliure) en mm. Default 0")
    parser.add_argument("--creep", type=float, default=0.0, help="Compensation creep en mm par feuille physique (0 = désactivé).")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()

    if args.input is None:
        print("Fichier d'entrée requis.")
        sys.exit(2)
    input_path = args.input
    if args.output is None:
        outp = Path(Path(input_path).stem + " - Booklet.pdf")
    else:
        outp = Path(args.output)

    if args.verbose:
        print(f"[+] input_path = {input_path}")
        print(f"[+] output_path = {outp}")

    try:
        sheets_pages = args.sheets * 4
        create_booklet_pdf(
            str(input_path),
            str(outp),
            paper=args.paper,
            signature=sheets_pages,
            gutter_mm=args.gutter,
            creep_mm=args.creep,
            book=args.book,
            verbose=args.verbose
        )
    except Exception as exc:
        print("Erreur lors de la génération du booklet :", exc)
        raise

    if args.verbose:
        print("[+] Terminé.")
