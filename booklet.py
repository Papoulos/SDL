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
    --signature N       pages par carnet (multiple de 4). Default 16
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

def generate_test_pdf(path: str, pages: int = 20, paper="A4", grid: bool = False):
    """
    Génère un PDF de test numéroté, avec repères, et option quadrillage 1 mm.
    - grid=False : version simple (cadre + numéro + repères)
    - grid=True  : quadrillage 1 mm (très fin) + graduations tous les 10 mm (traits + labels)
    """
    if paper.upper() == "A4":
        w_pt = A4_WIDTH_PT
        h_pt = A4_HEIGHT_PT
        w_mm = 210.0
        h_mm = 297.0
    else:
        w_pt = LETTER_WIDTH_PT
        h_pt = LETTER_HEIGHT_PT
        # approximations pour letter in mm
        w_mm = 216.0
        h_mm = 279.0

    doc = fitz.open()

    # grid styling
    grid_line_width = 0.15  # very thin
    grid_color = (0.85, 0.85, 0.85)  # light gray
    major_line_width = 0.5
    major_color = (0.6, 0.6, 0.6)  # darker gray
    tick_color = (1, 0, 0)  # red ticks for edges
    label_color = (0, 0, 0)

    # conversion helper: mm -> points
    def mm2pt(mm): return mm_to_pt(mm)

    # Precompute counts
    cols = int(math.floor(w_mm))  # approx number of mm columns
    rows = int(math.floor(h_mm))

    for p in range(1, pages + 1):
        pg = doc.new_page(width=w_pt, height=h_pt)

        # simple frame
        pg.draw_rect(fitz.Rect(10, 10, w_pt - 10, h_pt - 10), color=(0.8, 0.8, 0.8), width=0.6)

        # big centered page number
        rc = fitz.Rect(0, 0, w_pt, h_pt)
        pg.insert_textbox(rc, f"PAGE {p}", fontsize=56, fontname="helv", align=1)

        # small edge ticks to visual check
        pg.draw_line(p1=(mm2pt(5), mm2pt(5)), p2=(mm2pt(15), mm2pt(5)), color=(0, 0, 1), width=1.0)
        pg.draw_line(p1=(mm2pt(5), h_pt - mm2pt(5)), p2=(mm2pt(15), h_pt - mm2pt(5)), color=(0, 0, 1), width=1.0)

        if grid:
            # draw 1 mm vertical grid lines
            x = 0.0
            # draw as lines across page height
            for i in range(0, int(math.ceil(w_mm)) + 1):
                x_pt = mm2pt(i)
                # choose major line every 10 mm
                if i % 10 == 0:
                    pg.draw_line(p1=(x_pt, 0), p2=(x_pt, h_pt), color=major_color, width=major_line_width)
                else:
                    pg.draw_line(p1=(x_pt, 0), p2=(x_pt, h_pt), color=grid_color, width=grid_line_width)
            # draw 1 mm horizontal grid lines
            for j in range(0, int(math.ceil(h_mm)) + 1):
                y_pt = mm2pt(j)
                if j % 10 == 0:
                    pg.draw_line(p1=(0, y_pt), p2=(w_pt, y_pt), color=major_color, width=major_line_width)
                else:
                    pg.draw_line(p1=(0, y_pt), p2=(w_pt, y_pt), color=grid_color, width=grid_line_width)

            # draw rulers (numbers) along top and left every 10 mm
            for i in range(0, int(math.ceil(w_mm / 10.0)) + 1):
                xm = i * 10
                x_pt = mm2pt(xm)
                label = str(xm)
                # top label (rotate none, small)
                pg.insert_text((x_pt + mm2pt(1), mm2pt(2)), label, fontsize=6, fontname="helv", color=label_color)
                # small tick
                pg.draw_line(p1=(x_pt, 0), p2=(x_pt, mm2pt(3)), color=tick_color, width=0.8)

            for j in range(0, int(math.ceil(h_mm / 10.0)) + 1):
                ym = j * 10
                y_pt = mm2pt(ym)
                label = str(ym)
                # left label
                pg.insert_text((mm2pt(1), y_pt + mm2pt(1)), label, fontsize=6, fontname="helv", color=label_color)
                # small tick
                pg.draw_line(p1=(0, y_pt), p2=(mm2pt(3), y_pt), color=tick_color, width=0.8)

            # draw corner cut marks for reference (5mm from corners)
            c = 5
            # top-left corner
            pg.draw_line(p1=(mm2pt(c), 0), p2=(mm2pt(c), mm2pt(8)), color=(0,0,0), width=0.8)
            pg.draw_line(p1=(0, mm2pt(c)), p2=(mm2pt(8), mm2pt(c)), color=(0,0,0), width=0.8)
            # top-right
            pg.draw_line(p1=(w_pt - mm2pt(c), 0), p2=(w_pt - mm2pt(c), mm2pt(8)), color=(0,0,0), width=0.8)
            pg.draw_line(p1=(w_pt - mm2pt(8), mm2pt(c)), p2=(w_pt, mm2pt(c)), color=(0,0,0), width=0.8)
            # bottom-left
            pg.draw_line(p1=(mm2pt(c), h_pt), p2=(mm2pt(c), h_pt - mm2pt(8)), color=(0,0,0), width=0.8)
            pg.draw_line(p1=(0, h_pt - mm2pt(c)), p2=(mm2pt(8), h_pt - mm2pt(c)), color=(0,0,0), width=0.8)
            # bottom-right
            pg.draw_line(p1=(w_pt - mm2pt(c), h_pt), p2=(w_pt - mm2pt(c), h_pt - mm2pt(8)), color=(0,0,0), width=0.8)
            pg.draw_line(p1=(w_pt - mm2pt(8), h_pt - mm2pt(c)), p2=(w_pt, h_pt - mm2pt(c)), color=(0,0,0), width=0.8)

    doc.save(path)
    doc.close()

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

# ---------------- création de la tranche ----------------

CONFIG_FILE = "config.json"
FONT_CACHE_DIR = Path(tempfile.gettempdir())
FONT_CACHE_NAME = "booklet_font_cache.ttf"
FONT_CACHE_PATH = FONT_CACHE_DIR / FONT_CACHE_NAME

def load_config(verbose=False):
    """Charge la configuration depuis config.json."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        if verbose:
            print(f"[+] Configuration chargée depuis {CONFIG_FILE}")
        return config
    except FileNotFoundError:
        raise RuntimeError(f"Fichier de configuration '{CONFIG_FILE}' introuvable.")
    except json.JSONDecodeError:
        raise RuntimeError(f"Erreur de syntaxe dans '{CONFIG_FILE}'.")

def download_font(url, verbose=False):
    """Télécharge la police si elle n'est pas déjà en cache."""
    if FONT_CACHE_PATH.exists():
        if verbose:
            print(f"[+] Police déjà en cache : {FONT_CACHE_PATH}")
        return str(FONT_CACHE_PATH)

    if verbose:
        print(f"[+] Téléchargement de la police depuis {url}...")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        with open(FONT_CACHE_PATH, "wb") as f:
            f.write(response.content)
        if verbose:
            print(f"[+] Police sauvegardée dans {FONT_CACHE_PATH}")
        return str(FONT_CACHE_PATH)
    except requests.RequestException as e:
        raise RuntimeError(f"Erreur lors du téléchargement de la police : {e}")

def add_spine_to_cover(cover_path, input_filename, verbose=False):
    """
    Génère la tranche avec :
    - Un cadre noir de taille A5 (hauteur 210mm)
    - Un texte centré en longueur ET en épaisseur (via ajustement des coordonnées).
    """
    config = load_config(verbose=verbose)
    
    # --- 1. Chargement Police ---
    try:
        font_path = download_font(config.get("font_url"), verbose=verbose)
        font_buffer = Path(font_path).read_bytes()
        font_name = "customfont"
        has_custom_font = True
    except Exception:
        font_name = "helv"
        has_custom_font = False

    # --- 2. Dimensions Tranche ---
    spine_width_mm = config.get("spine_width_mm", 20)
    text = config.get("text", "")
    if not text:
        text = input_filename.replace('_', ' ').replace('-', ' ')

    spine_width_pt = mm_to_pt(spine_width_mm)
    spine_height_mm = 210.0  # Hauteur A5 fixe
    spine_height_pt = mm_to_pt(spine_height_mm)

    spine_doc = fitz.open()
    spine_page = spine_doc.new_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)

    # Rectangle GLOBAL de la tranche (centré sur la page A4)
    x0 = (A4_WIDTH_PT - spine_width_pt) / 2
    y0 = (A4_HEIGHT_PT - spine_height_pt) / 2
    x1 = x0 + spine_width_pt
    y1 = y0 + spine_height_pt
    spine_rect = fitz.Rect(x0, y0, x1, y1)

    # Dessin du cadre noir
    spine_page.draw_rect(spine_rect, color=(0, 0, 0), width=1.0)

    # --- 3. Calcul Taille Police (75% de la hauteur) ---
    target_text_len = spine_height_pt * 0.75

    if has_custom_font:
        spine_page.insert_font(fontname=font_name, fontbuffer=font_buffer)
        temp_font = fitz.Font(fontbuffer=font_buffer)
    else:
        temp_font = fitz.Font("helv")

    len_at_1 = temp_font.text_length(text, fontsize=1)
    if len_at_1 > 0:
        fontsize = target_text_len / len_at_1
    else:
        fontsize = 24

    # Sécurité : empécher que le texte soit plus gros que l'épaisseur de la tranche
    max_thickness = spine_width_pt * 0.85
    if fontsize > max_thickness:
        fontsize = max_thickness

    # --- 4. Centrage du texte (Correction) ---
    # Pour bien centrer le texte dans l'épaisseur, on crée un rectangle "textbox"
    # qui fait exactement la hauteur de la police (fontsize) et qui est centré
    # horizontalement dans le rectangle de la tranche.
    
    text_rect_width = fontsize * 1.2  # Un peu de marge pour les descendeurs
    offset_x = (spine_width_pt - text_rect_width) / 2
    
    # Rectangle spécifiquement pour contenir le texte
    text_rect = fitz.Rect(
        spine_rect.x0 + offset_x,     # Décalé pour être au milieu de l'épaisseur
        spine_rect.y0,                # Haut du A5
        spine_rect.x0 + offset_x + text_rect_width, 
        spine_rect.y1                 # Bas du A5
    )

    # Debug: afficher le rectangle de texte en rouge pour vérifier le centrage (commenter après test)
    # spine_page.draw_rect(text_rect, color=(1,0,0), width=0.5)

    spine_page.insert_textbox(
        text_rect,
        text,
        fontsize=fontsize,
        fontname=font_name,
        align=fitz.TEXT_ALIGN_CENTER, # Centre le texte dans la longueur (Y)
        rotate=90                     # Tourne le texte
    )

    # --- 5. Sauvegarde ---
    spine_pdf_bytes = spine_doc.tobytes()
    spine_doc.close()

    cover_doc = fitz.open(cover_path)
    final_doc = fitz.open()
    
    if cover_doc.page_count >= 1:
        final_doc.insert_pdf(cover_doc, from_page=0, to_page=0)
    
    spine_inserter = fitz.open("pdf", spine_pdf_bytes)
    final_doc.insert_pdf(spine_inserter)
    
    if cover_doc.page_count >= 2:
        final_doc.insert_pdf(cover_doc, from_page=1, to_page=1)

    final_doc.save(cover_path, garbage=4, deflate=True)
    final_doc.close()
    cover_doc.close()

    if verbose:
        print(f"[+] Tranche ajoutée avec succès à '{cover_path}'.")


# ---------------- création du booklet ----------------

def create_cover_pdf(cover_path, first_page_tuple, last_page_tuple, verbose=False):
    """
    Crée un PDF Cover avec des marges asymétriques pour la reliure.
    - Front : Droite 3.2cm / Gauche 1.0cm
    - Back  : Gauche 3.2cm / Droite 1.0cm
    - Haut/Bas : 1.0cm (pour équilibrer avec la petite marge)
    """
    if verbose:
        print(f"[+] Création du PDF couverture (Marges asymétriques) : {cover_path}")

    w_pt = A4_WIDTH_PT
    h_pt = A4_HEIGHT_PT
    
    # Définition des marges en points
    margin_large_pt = mm_to_pt(32.0) # 3.2 cm
    margin_small_pt = mm_to_pt(10.0) # 1.0 cm
    
    out_doc = fitz.open()

    def draw_page_content(page_source_tuple, is_front):
        sdoc, spno = page_source_tuple
        pg = out_doc.new_page(width=w_pt, height=h_pt)
        
        # Calcul des coordonnées du cadre selon si c'est Front ou Back
        if is_front:
            # Front : Gauche=Small, Droite=Large
            x0 = margin_small_pt
            x1 = w_pt - margin_large_pt
        else:
            # Back : Gauche=Large, Droite=Small
            x0 = margin_large_pt
            x1 = w_pt - margin_small_pt
            
        # Haut/Bas : on utilise la marge petite (1cm) pour maximiser l'espace
        y0 = margin_small_pt
        y1 = h_pt - margin_small_pt
        
        border_rect = fitz.Rect(x0, y0, x1, y1)
        
        # 1. Dessiner le cadre noir
        pg.draw_rect(border_rect, color=(0, 0, 0), width=1.0)
        
        # 2. Zone sûre (padding interne 1mm)
        pad = mm_to_pt(1.0)
        safe_rect = fitz.Rect(
            border_rect.x0 + pad,
            border_rect.y0 + pad,
            border_rect.x1 - pad,
            border_rect.y1 - pad
        )

        # 3. Placer le PDF source
        src_rect = sdoc[spno].rect
        placed_rect = fit_src_rect_into_target(safe_rect, src_rect, scale_mode="fit")
        pg.show_pdf_page(placed_rect, sdoc, spno)

    # Page 1: Front (is_front=True)
    draw_page_content(first_page_tuple, is_front=True)

    # Page 2: Back (is_front=False)
    draw_page_content(last_page_tuple, is_front=False)

    out_doc.save(cover_path)
    out_doc.close()

def create_booklet_pdf(input_path, output_path, paper="A4", signature=16, gutter_mm=0.0,
                       pad_mode="blank", overlap_mm=0.2, scale_mode="fit",
                       creep_mm: float = 0.0,
                       book: bool = False,
                       verbose=False, debug_rects=False, cover_path=None):
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
            first_page = pages[0]
            last_page = pages[-1]
            if cover_path:
                create_cover_pdf(cover_path, first_page, last_page, verbose=verbose)

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
                if debug_rects:
                    page_recto.draw_rect(target_rect, color=(0,0,0), width=0.4)
                    page_recto.draw_rect(placed_rect, color=(1,0,0), width=0.6)
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
                if debug_rects:
                    page_recto.draw_rect(target_rect, color=(0,0,0), width=0.4)
                    page_recto.draw_rect(placed_rect, color=(0,0,1), width=0.6)
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
                placed_rect = fit_src_rect_into_target(target_rect, src_rect, scale_mode=scale_mode)
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
    parser.add_argument("input", nargs="?", help="PDF d'entrée (source A4 attendu). Si --test utilisé, peut être omis.")
    parser.add_argument("output", nargs="?", help="PDF de sortie (optionnel). Si absent -> '<input_stem> - Booklet.pdf' or 'Test - Booklet.pdf' for --test")
    parser.add_argument("--signature", type=int, default=16, help="Pages par carnet (multiple de 4). Default 16")
    parser.add_argument("--book", action="store_true", help="Ajoute deux pages blanches recto verso au début et à la fin pour la reliure.")
    parser.add_argument("--paper", type=str, default="A4", help="Paper target (A4 or Letter). Default A4")
    parser.add_argument("--gutter", type=float, default=0.0, help="Gutter (pliure) en mm. Default 0")
    parser.add_argument("--pad", type=str, choices=["blank", "last"], default="blank", help="Comment padder le dernier carnet. Default blank")
    parser.add_argument("--overlap-mm", type=float, default=0.2, help="Micro-chevauchement central en mm. Default 0.2")
    parser.add_argument("--scale-mode", type=str, choices=["fit", "fill"], default="fit", help="fit conserve ratio; fill occupe tout l'espace A5 (déforme)")
    parser.add_argument("--creep", type=float, default=0.0, help="Compensation creep en mm par feuille physique (0 = désactivé).")
    parser.add_argument("--test", action="store_true", help="Génère un PDF de test et l'utilise comme source (pratique pour calibration).")
    parser.add_argument("--test-pages", type=int, default=20, help="Nombre de pages pour le PDF de test (default 20).")
    parser.add_argument("--test-grid", action="store_true", help="Ajoute un quadrillage 1 mm + graduations 10 mm au PDF de test.")
    parser.add_argument("--debug-rects", action="store_true", help="Dessine rectangles cible/placé (debug).")
    parser.add_argument("--cover", action="store_true", help="Ajoute une tranche (spine) au fichier de couverture (nécessite --book).")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()

    temp_test_path = None
    if args.test:
        fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        temp_test_path = tmp_path
        if args.verbose:
            print(f"[+] Génération d'un PDF de test {tmp_path} ({args.test_pages} pages)...")
        generate_test_pdf(tmp_path, pages=args.test_pages, paper=args.paper, grid=args.test_grid)
        input_path = tmp_path
        if args.output is None:
            outp = Path(f"Test - Booklet.pdf")
        else:
            outp = Path(args.output)
    else:
        if args.input is None:
            print("Fichier d'entrée requis si --test n'est pas utilisé.")
            sys.exit(2)
        input_path = args.input
        if args.output is None:
            outp = Path(Path(input_path).stem + " - Booklet.pdf")
        else:
            outp = Path(args.output)

    cover_outp = None
    if args.book:
        stem = outp.stem
        if stem.endswith(" - Booklet"):
            stem = stem[:-9]
        cover_outp = outp.with_name(stem + " - Cover.pdf")


    if args.signature % 4 != 0:
        print("La signature doit être multiple de 4.")
        sys.exit(2)

    if args.verbose:
        print(f"[+] input_path = {input_path}")
        print(f"[+] output_path = {outp}")
        if cover_outp:
            print(f"[+] cover_output_path = {cover_outp}")

    try:
        create_booklet_pdf(
            str(input_path),
            str(outp),
            paper=args.paper,
            signature=args.signature,
            gutter_mm=args.gutter,
            pad_mode=args.pad,
            overlap_mm=args.overlap_mm,
            scale_mode=args.scale_mode,
            creep_mm=args.creep,
            book=args.book,
            verbose=args.verbose,
            debug_rects=args.debug_rects,
            cover_path=str(cover_outp) if cover_outp else None
        )
    except Exception as exc:
        print("Erreur lors de la génération du booklet :", exc)
        raise
    finally:
        if temp_test_path:
            try:
                os.remove(temp_test_path)
            except Exception:
                pass

    if args.cover and args.book and cover_outp and Path(cover_outp).exists():
        if args.verbose:
            print(f"[+] Ajout de la tranche au fichier de couverture : {cover_outp}")
        try:
            add_spine_to_cover(
                cover_path=str(cover_outp),
                input_filename=Path(input_path).stem,
                verbose=args.verbose
            )
        except Exception as exc:
            print(f"Erreur lors de l'ajout de la tranche : {exc}")

    if args.verbose:
        print("[+] Terminé.")
