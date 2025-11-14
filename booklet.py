#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
booklet.py

Génère un livret (booklet) prêt à l'impression en mode "pliure".
- Par défaut : signature = 16 (4 feuilles), paper = A4, gutter = 0 mm, margin = 0 mm, overlap = 0.2 mm
- Chaque page source est scalée au maximum dans la demi-feuille disponible en conservant le ratio.

Usage:
    python booklet.py input.pdf output_booklet.pdf [--signature 16] [--paper A4] [--gutter 0]
        [--pad blank|last] [--overlap-mm 0.2] [--verbose] [--debug-rects]

Dependencies:
    pip install pymupdf
"""
from pathlib import Path
import argparse
import sys

try:
    import fitz  # PyMuPDF
except Exception:
    print("PyMuPDF (fitz) requis. Installer: pip install pymupdf")
    raise

# Points conversion
MM_TO_PT = 72.0 / 25.4

def mm_to_pt(mm: float) -> float:
    return mm * MM_TO_PT

# Paper sizes (portrait) in points
A4_WIDTH_PT = 595.276
A4_HEIGHT_PT = 841.89

LETTER_WIDTH_PT = 612.0
LETTER_HEIGHT_PT = 792.0

# ---------------- utilities ----------------

def smallest_multiple_of_4_ge(n: int) -> int:
    if n <= 0:
        return 0
    return ((n + 3) // 4) * 4

def make_blank_page(width_pt, height_pt):
    tmp = fitz.open()
    tmp.new_page(width=width_pt, height=height_pt)
    return tmp

# ---------------- geometry / scaling ----------------

def compute_embed_rects(page_width: float, page_height: float, gutter_pt: float, margin_tlbr, overlap_pt: float = 0.0):
    """
    Retourne deux fitz.Rect (left, right) pour placer 2 A5 sur une page landscape.
    Si gutter_pt == 0, on applique overlap_pt (points) en élargissant/chevauchant les moitiés.
    """
    top, leftm, bottom, rightm = margin_tlbr
    inner_width = page_width - leftm - rightm
    inner_height = page_height - top - bottom

    half_w = inner_width / 2.0

    if gutter_pt == 0:
        # Étendre légèrement les moitiés pour chevauchement symétrique
        left_x0 = leftm
        left_x1 = leftm + half_w + (overlap_pt / 2.0)
        right_x0 = leftm + half_w - (overlap_pt / 2.0)
        right_x1 = leftm + 2 * half_w
        y0 = top
        y1 = top + inner_height
        rect_left = fitz.Rect(left_x0, y0, left_x1, y1)
        rect_right = fitz.Rect(right_x0, y0, right_x1, y1)
        return rect_left, rect_right

    # gutter > 0: séparer par offset
    offset = gutter_pt / 2.0
    left_x0 = leftm - offset
    left_x1 = leftm + half_w - offset
    right_x0 = leftm + half_w + offset
    right_x1 = leftm + 2 * half_w + offset

    # possibilité d'un overlap réduit même avec gutter
    if overlap_pt > 0:
        left_x1 += overlap_pt / 2.0
        right_x0 -= overlap_pt / 2.0

    y0 = top
    y1 = top + inner_height
    rect_left = fitz.Rect(left_x0, y0, left_x1, y1)
    rect_right = fitz.Rect(right_x0, y0, right_x1, y1)
    return rect_left, rect_right

def fit_src_rect_into_target(target_rect: fitz.Rect, src_rect: fitz.Rect):
    """
    Retourne un fitz.Rect placé à l'intérieur de target_rect qui contient la page source
    mise à l'échelle uniformément au maximum tout en conservant l'aspect ratio.
    On centre le résultat dans target_rect.
    """
    target_w = target_rect.width
    target_h = target_rect.height
    src_w = src_rect.width
    src_h = src_rect.height

    if src_w <= 0 or src_h <= 0:
        # valeur par défaut: remplir complètement le target
        return target_rect

    scale = min(target_w / src_w, target_h / src_h)

    new_w = src_w * scale
    new_h = src_h * scale

    # centre dans target_rect
    x0 = target_rect.x0 + (target_w - new_w) / 2.0
    y0 = target_rect.y0 + (target_h - new_h) / 2.0
    x1 = x0 + new_w
    y1 = y0 + new_h

    return fitz.Rect(x0, y0, x1, y1)

# ---------------- booklet splitting & imposition ----------------

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

# ---------------- main create function ----------------

def create_booklet_pdf(input_path, output_path, paper="A4", signature=16, gutter_mm=0.0,
                       pad_mode="blank", overlap_mm=0.2, verbose=False, debug_rects=False):
    in_doc = fitz.open(input_path)
    if in_doc.needs_pass:
        raise RuntimeError("Le PDF d'entrée est protégé / chiffré. Impossible de poursuivre.")

    # paper sizes
    if paper.upper() == "A4":
        portrait_w = A4_WIDTH_PT
        portrait_h = A4_HEIGHT_PT
    elif paper.upper() in ("LETTER", "USLETTER", "LETTER-8.5X11"):
        portrait_w = LETTER_WIDTH_PT
        portrait_h = LETTER_HEIGHT_PT
    else:
        raise ValueError("Paper only A4 or Letter supported for now")

    landscape_w = portrait_h
    landscape_h = portrait_w

    if verbose:
        print(f"[+] Input pages: {len(in_doc)}")
        print(f"[+] Target paper: {paper} landscape {landscape_w:.1f} x {landscape_h:.1f} pts")

    pages = [(in_doc, pno) for pno in range(len(in_doc))]
    blank_doc = make_blank_page(portrait_w, portrait_h)

    booklets = split_into_booklets_minimize_last(pages, signature, blank_doc, pad_mode=pad_mode)
    if verbose:
        print(f"[+] Booklets: {len(booklets)} sizes: {[len(b) for b in booklets]}")

    out_doc = fitz.open()
    gutter_pt = mm_to_pt(gutter_mm)
    overlap_pt = mm_to_pt(overlap_mm)

    # default margins 0 as requested
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

        for sheet in sheets_pattern:
            lr, rr, lv, rv = sheet
            lr_i = lr - 1
            rr_i = rr - 1
            lv_i = lv - 1
            rv_i = rv - 1

            rect_left, rect_right = compute_embed_rects(landscape_w, landscape_h, gutter_pt, margin_pts, overlap_pt=overlap_pt)

            if verbose:
                print(f"[DEBUG] rect_left: {rect_left} rect_right: {rect_right} (gutter_mm={gutter_mm} overlap_mm={overlap_mm})")

            # --- Recto ---
            page_recto = out_doc.new_page(width=landscape_w, height=landscape_h)

            # left recto placement with scaling
            sdoc, spno = booklet[lr_i]
            try:
                src_rect = sdoc[spno].rect
                target_rect = rect_left
                placed_rect = fit_src_rect_into_target(target_rect, src_rect)
                if debug_rects:
                    page_recto.draw_rect(target_rect, color=(0,0,0), width=0.4)  # target border
                    page_recto.draw_rect(placed_rect, color=(1,0,0), width=0.6)   # placed content border
                page_recto.show_pdf_page(placed_rect, sdoc, spno)
            except Exception as e:
                if verbose:
                    print(f"[!] Warning inserting recto-left: {e}")

            # right recto placement with scaling
            sdoc, spno = booklet[rr_i]
            try:
                src_rect = sdoc[spno].rect
                target_rect = rect_right
                placed_rect = fit_src_rect_into_target(target_rect, src_rect)
                if debug_rects:
                    page_recto.draw_rect(target_rect, color=(0,0,0), width=0.4)
                    page_recto.draw_rect(placed_rect, color=(0,0,1), width=0.6)
                page_recto.show_pdf_page(placed_rect, sdoc, spno)
            except Exception as e:
                if verbose:
                    print(f"[!] Warning inserting recto-right: {e}")

            # --- Verso ---
            page_verso = out_doc.new_page(width=landscape_w, height=landscape_h)

            sdoc, spno = booklet[lv_i]
            try:
                src_rect = sdoc[spno].rect
                target_rect = rect_left
                placed_rect = fit_src_rect_into_target(target_rect, src_rect)
                if debug_rects:
                    page_verso.draw_rect(target_rect, color=(0,0,0), width=0.4)
                    page_verso.draw_rect(placed_rect, color=(1,0,0), width=0.6)
                page_verso.show_pdf_page(placed_rect, sdoc, spno)
            except Exception as e:
                if verbose:
                    print(f"[!] Warning inserting verso-left: {e}")

            sdoc, spno = booklet[rv_i]
            try:
                src_rect = sdoc[spno].rect
                target_rect = rect_right
                placed_rect = fit_src_rect_into_target(target_rect, src_rect)
                if debug_rects:
                    page_verso.draw_rect(target_rect, color=(0,0,0), width=0.4)
                    page_verso.draw_rect(placed_rect, color=(0,0,1), width=0.6)
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
    parser.add_argument("input", help="PDF d'entrée (source A4 attendu)")
    parser.add_argument("output", help="PDF de sortie (booklet)")
    parser.add_argument("--signature", type=int, default=16, help="Pages par carnet (multiple de 4). Default 16")
    parser.add_argument("--paper", type=str, default="A4", help="Paper target A4 or Letter. Default A4")
    parser.add_argument("--gutter", type=float, default=0.0, help="Gutter (pliure) en mm. Default 0")
    parser.add_argument("--pad", type=str, choices=["blank", "last"], default="blank", help="Comment padder le dernier carnet. Default blank")
    parser.add_argument("--overlap-mm", type=float, default=0.2, help="Micro-chevauchement central en mm (pour éliminer ligne blanche). Default 0.2")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--debug-rects", action="store_true", help="Dessine les rectangles cible/placé (utile pour debug).")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    inp = Path(args.input)
    outp = Path(args.output)

    if not inp.exists():
        print("Fichier d'entrée introuvable :", inp)
        sys.exit(2)
    if args.signature % 4 != 0:
        print("signature doit être multiple de 4")
        sys.exit(2)

    try:
        create_booklet_pdf(
            str(inp),
            str(outp),
            paper=args.paper,
            signature=args.signature,
            gutter_mm=args.gutter,
            pad_mode=args.pad,
            overlap_mm=args.overlap_mm,
            verbose=args.verbose,
            debug_rects=args.debug_rects
        )
    except Exception as exc:
        print("Erreur lors de la génération du booklet :", exc)
        raise
