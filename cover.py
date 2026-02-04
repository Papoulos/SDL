#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cover_generator_a5_stretch.py
- Redimensionne les pages Front et Back pour qu'elles fassent exactement 21 cm × 14,8 cm (A5), en déformant si nécessaire.
- Pas de cadre ni de lignes.
- Crée la zone pour le "spine".
"""

import sys
import os
import tempfile
import urllib.request
import json
from pathlib import Path
import fitz  # PyMuPDF

MM_TO_PT = 72 / 25.4
A4_WIDTH_PT = 595.276
A4_HEIGHT_PT = 841.89
A5_WIDTH_MM = 148.5  # 14.85 cm
A5_HEIGHT_MM = 210.0  # 21 cm
OVERHANG_MM = 2.5

def mm2pt(mm):
    return mm * MM_TO_PT

def hex_to_rgb(hex_str):
    """Convertit #RRGGBB en tuple (r, g, b)."""
    if not hex_str:
        return (0, 0, 0)
    hex_str = str(hex_str).strip().replace('#', '').lower()
    try:
        if len(hex_str) != 6:
            return (0, 0, 0)
        return tuple(int(hex_str[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    except:
        return (0, 0, 0)

def download_font(url):
    if not url:
        return None
    if "github.com" in url and "blob" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    fd, path = tempfile.mkstemp(suffix=".ttf")
    os.close(fd)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response, open(path, 'wb') as out_file:
            out_file.write(response.read())
        return path
    except Exception as e:
        print(f"[!] Erreur font: {e}")
        return None

def place_page_stretch(dest_page, src_doc, src_pno, target_rect):
    """Redimensionne la page source pour qu'elle remplisse exactement la zone cible, en déformant si nécessaire."""
    src_rect = src_doc[src_pno].rect
    # Redimensionner pour remplir exactement la zone cible (déformation possible)
    dest_page.show_pdf_page(target_rect, src_doc, src_pno, clip=src_rect, keep_proportion=False)

def make_cover(input_pdf, config_path, output_pdf, verbose=False):
    # --- Config ---
    cfg = {}
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except:
            pass

    spine_width_mm = float(cfg.get("spine_width_mm", 30))
    spine_text = (cfg.get("text") or "").strip() or Path(input_pdf).stem
    font_url = cfg.get("font_url")
    text_color_hex = cfg.get("text_color", "#000000")
    spine_color_hex = cfg.get("spine_color", "#FFFFFF")
    text_color_rgb = hex_to_rgb(text_color_hex)
    spine_color_rgb = hex_to_rgb(spine_color_hex)

    if verbose:
        print(f"Tranche: {spine_width_mm}mm | Couleur texte: {text_color_hex} | Couleur fond: {spine_color_hex} | Texte: '{spine_text}'")

    doc = fitz.open(input_pdf)
    if doc.page_count == 0:
        raise RuntimeError("PDF vide")

    out = fitz.open()

    # --- Dimensions ---
    a5_w_pt = mm2pt(A5_WIDTH_MM)
    a5_h_pt = mm2pt(A5_HEIGHT_MM)

    overhang_pt = mm2pt(OVERHANG_MM)

    # --- Page 1: Front sur A4 portrait ---
    page_front = out.new_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
    # Dépassement haut, bas et droit
    inner_front = fitz.Rect(
        (A4_WIDTH_PT - a5_w_pt) / 2,
        (A4_HEIGHT_PT - a5_h_pt) / 2 - overhang_pt,
        (A4_WIDTH_PT - a5_w_pt) / 2 + a5_w_pt + overhang_pt,
        (A4_HEIGHT_PT - a5_h_pt) / 2 + a5_h_pt + overhang_pt
    )
    place_page_stretch(page_front, doc, 0, inner_front)

    # --- Page 2: Back sur A4 portrait ---
    page_back = out.new_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
    # Dépassement haut, bas et GAUCHE (côté extérieur)
    inner_back = fitz.Rect(
        (A4_WIDTH_PT - a5_w_pt) / 2 - overhang_pt,
        (A4_HEIGHT_PT - a5_h_pt) / 2 - overhang_pt,
        (A4_WIDTH_PT - a5_w_pt) / 2 + a5_w_pt,
        (A4_HEIGHT_PT - a5_h_pt) / 2 + a5_h_pt + overhang_pt
    )
    place_page_stretch(page_back, doc, doc.page_count - 1, inner_back)

    # --- Page 3: Spine sur A4 portrait ---
    page_spine = out.new_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
    spine_w_pt = mm2pt(spine_width_mm)
    spine_center_x = A4_WIDTH_PT / 2
    # Dépassement haut et bas uniquement
    spine_rect = fitz.Rect(
        spine_center_x - spine_w_pt / 2,
        A4_HEIGHT_PT / 2 - a5_h_pt / 2 - overhang_pt,
        spine_center_x + spine_w_pt / 2,
        A4_HEIGHT_PT / 2 + a5_h_pt / 2 + overhang_pt
    )

    # Remplir la zone de la tranche avec la couleur de fond
    page_spine.draw_rect(spine_rect, fill=spine_color_rgb, width=0)

    # Police
    fontfile = None
    custom_fontname = "spinefont"
    if font_url:
        fontfile = download_font(font_url)
        if fontfile:
            try:
                page_spine.insert_font(fontname=custom_fontname, fontfile=fontfile)
                if verbose:
                    print(f"Police custom enregistrée sous '{custom_fontname}'")
            except Exception as e:
                if verbose:
                    print(f"Erreur enregistrement police: {e}")
                fontfile = None

    # --- CALCUL DE CENTRAGE pour texte spine ---
    padding_x = mm2pt(1)
    padding_y = mm2pt(5)
    if spine_width_mm < 20:
        padding_x = 0
        if verbose:
            print("Padding_x set to 0 for narrow spine")

    text_rect = fitz.Rect(
        spine_rect.x0 + padding_x,
        spine_rect.y0 + padding_y,
        spine_rect.x1 - padding_x,
        spine_rect.y1 - padding_y
    )

    # Chargement police pour métriques
    temp_font = None
    try:
        temp_font = fitz.Font(fontfile=fontfile) if fontfile else fitz.Font("helv")
    except Exception as e:
        if verbose:
            print(f"Erreur chargement temp_font: {e}")
        temp_font = fitz.Font("helv")

    # Facteur hauteur de ligne
    line_height_factor = temp_font.ascender - temp_font.descender + 0.2
    text_len_1 = 1
    try:
        text_len_1 = temp_font.text_length(spine_text, fontsize=1) or 1
    except Exception as e:
        if verbose:
            print(f"Erreur text_length: {e} → fallback to 1")

    available_height = text_rect.height
    max_font_length = (available_height * 0.9) / text_len_1
    max_font_height = text_rect.width * 0.95
    start_fontsize = min(max_font_height, max_font_length)

    # Insertion texte
    fontsize = start_fontsize
    success = False
    for i in range(50):
        try:
            rc = page_spine.insert_textbox(
                text_rect,
                spine_text,
                fontsize=fontsize,
                fontname=custom_fontname if fontfile else "helv",
                align=fitz.TEXT_ALIGN_CENTER,
                rotate=90,
                color=text_color_rgb
            )
            if rc >= 0:
                success = True
                if verbose:
                    print(f"Texte centré inséré (taille {fontsize:.2f})")
                break
        except Exception as e:
            if verbose:
                print(f"Erreur essai {i}: {e}")
        fontsize *= 0.95

    # Fallback
    if not success:
        print("[!] Fallback Helvetica")
        try:
            page_spine.insert_textbox(
                text_rect,
                spine_text,
                fontsize=14,
                fontname="helv",
                color=text_color_rgb,
                rotate=90,
                align=fitz.TEXT_ALIGN_CENTER
            )
        except:
            pass

    if fontfile and os.path.exists(fontfile):
        try:
            os.remove(fontfile)
        except:
            pass

    out.save(output_pdf)
    out.close()
    doc.close()
    if verbose:
        print(f"Terminé → {output_pdf}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python cover_generator_a5_stretch.py input.pdf [config.json] [output_cover.pdf]")
        sys.exit(1)

    input_pdf = sys.argv[1]

    # Sortie & Config auto...
    if len(sys.argv) >= 3 and sys.argv[-1].lower().endswith(".pdf") and "config" not in sys.argv[-1]:
        output_pdf = sys.argv[-1]
        conf_idx = 2 if len(sys.argv) == 4 else None
    else:
        output_pdf = f"{Path(input_pdf).stem} - Cover.pdf"
        conf_idx = 2 if len(sys.argv) == 3 else None

    config_path = None
    if conf_idx:
        config_path = sys.argv[conf_idx]

    if not config_path:
        d = os.path.dirname(input_pdf) or "."
        if os.path.exists(os.path.join(d, "config.json")):
            config_path = os.path.join(d, "config.json")
        elif os.path.exists("config.json"):
            config_path = "config.json"

    make_cover(input_pdf, config_path, output_pdf, verbose=True)

if __name__ == "__main__":
    main()
