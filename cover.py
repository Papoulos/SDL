#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cover_generator_asymmetric_v2.py
Version finale : texte tranche parfaitement centré + police custom 100% fiable
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
A5_WIDTH_MM = 148.0
A5_HEIGHT_MM = 210.0

def mm2pt(mm): return mm * MM_TO_PT

def download_font(url):
    if not url:
        return None
    if "github.com" in url and "blob" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    fd, path = tempfile.mkstemp(suffix=".ttf")
    os.close(fd)
    urllib.request.urlretrieve(url, path)
    return path

def place_page_scaled_center(dest_page, src_doc, src_pno, target_rect):
    src_page = src_doc[src_pno]
    src_rect = src_page.rect
    scale = min(target_rect.width / src_rect.width, target_rect.height / src_rect.height)
    new_w = src_rect.width * scale
    new_h = src_rect.height * scale
    x = target_rect.x0 + (target_rect.width - new_w) / 2
    y = target_rect.y0 + (target_rect.height - new_h) / 2
    dest_page.show_pdf_page(fitz.Rect(x, y, x + new_w, y + new_h), src_doc, src_pno)

def make_cover(input_pdf, config_path, output_pdf, verbose=False):
    cfg = {}
    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

    spine_width_mm = float(cfg.get("spine_width_mm", 30))
    spine_text = (cfg.get("text") or "").strip() or Path(input_pdf).stem
    font_url = cfg.get("font_url")

    doc = fitz.open(input_pdf)
    if doc.page_count == 0:
        raise RuntimeError("Le PDF d'entrée est vide")
    out = fitz.open()

    # ===================================================================
    # Dimensions
    # ===================================================================
    LEFT_MARGIN_FRONT_MM = 10.0   # 1 cm gauche front
    RIGHT_MARGIN_BACK_MM = 10.0   # 1 cm droite back
    OTHER_MARGINS_MM     = 32.0   # 3.2 cm partout ailleurs
    SPINE_MARGIN_MM      = 32.0   # 3.2 cm autour tranche

    a5_w_pt = mm2pt(A5_WIDTH_MM)
    a5_h_pt = mm2pt(A5_HEIGHT_MM)

    # ===================================================================
    # FRONT + BACK (inchangé, juste plus propre)
    # ===================================================================
    # Front
    page_front = out.new_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
    outer_w_f = a5_w_pt + mm2pt(LEFT_MARGIN_FRONT_MM + OTHER_MARGINS_MM)
    outer_h   = a5_h_pt + mm2pt(OTHER_MARGINS_MM * 2)
    outer_front = fitz.Rect((A4_WIDTH_PT - outer_w_f)/2, (A4_HEIGHT_PT - outer_h)/2,
                            (A4_WIDTH_PT - outer_w_f)/2 + outer_w_f, (A4_HEIGHT_PT - outer_h)/2 + outer_h)
    inner_front = outer_front + (mm2pt(LEFT_MARGIN_FRONT_MM), mm2pt(OTHER_MARGINS_MM),
                                -mm2pt(OTHER_MARGINS_MM), -mm2pt(OTHER_MARGINS_MM))
    page_front.draw_rect(outer_front, color=(0,0,0), width=1.5)
    place_page_scaled_center(page_front, doc, 0, inner_front)

    # Back
    page_back = out.new_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
    outer_w_b = a5_w_pt + mm2pt(RIGHT_MARGIN_BACK_MM + OTHER_MARGINS_MM)
    outer_back = fitz.Rect((A4_WIDTH_PT - outer_w_b)/2, (A4_HEIGHT_PT - outer_h)/2,
                           (A4_WIDTH_PT - outer_w_b)/2 + outer_w_b, (A4_HEIGHT_PT - outer_h)/2 + outer_h)
    inner_back = outer_back + (mm2pt(OTHER_MARGINS_MM), mm2pt(OTHER_MARGINS_MM),
                               -mm2pt(RIGHT_MARGIN_BACK_MM), -mm2pt(OTHER_MARGINS_MM))
    page_back.draw_rect(outer_back, color=(0,0,0), width=1.5)
    place_page_scaled_center(page_back, doc, doc.page_count-1, inner_back)

    # ====================== SPINE – Version finale qui marche partout ======================
    page_spine = out.new_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
    spine_w_pt = mm2pt(spine_width_mm)
    spine_rect = fitz.Rect(A4_WIDTH_PT/2 - spine_w_pt/2,
                           A4_HEIGHT_PT/2 - a5_h_pt/2,
                           A4_WIDTH_PT/2 + spine_w_pt/2,
                           A4_HEIGHT_PT/2 + a5_h_pt/2)

    outer_spine = spine_rect + (-mm2pt(SPINE_MARGIN_MM), -mm2pt(SPINE_MARGIN_MM),
                                mm2pt(SPINE_MARGIN_MM), mm2pt(SPINE_MARGIN_MM))
    page_spine.draw_rect(outer_spine, color=0, width=1.5)
    page_spine.draw_rect(spine_rect, color=0, width=1)

    # Téléchargement police custom
    fontfile = None
    if font_url:
        try:
            fontfile = download_font(font_url)
            if verbose:
                print(f"Police custom téléchargée et prête : {fontfile}")
        except Exception as e:
            fontfile = None
            if verbose:
                print("Échec téléchargement police → Helvetica", e)

    # Texte de la tranche
    text = spine_text or Path(input_pdf).stem

    # Zone où on écrit (un peu de padding)
    padding = mm2pt(7)
    text_rect = spine_rect + (padding, padding, -padding, -padding)

    # Taille de police de départ
    fontsize = text_rect.height * 0.77

    success = False
    for _ in range(50):
        try:
            if fontfile:
                # Méthode qui marche à 100% avec police externe
                rc = page_spine.insert_textbox(
                    text_rect,
                    text,
                    fontsize=fontsize,
                    fontfile=fontfile,      # ← clé magique
                    align=fitz.TEXT_ALIGN_CENTER,
                    rotate=90,
                    color=0
                )
            else:
                # Helvetica standard
                rc = page_spine.insert_textbox(
                    text_rect,
                    text,
                    fontsize=fontsize,
                    fontname="helv",
                    align=fitz.TEXT_ALIGN_CENTER,
                    rotate=90,
                    color=0
                )
            if rc >= 0:  # le texte a tenu dans le rectangle
                success = True
                break
        except:
            pass
        fontsize *= 0.93

    if not success:
        # Secours absolu
        page_spine.insert_textbox(text_rect, text, fontsize=14, fontname="helv", color=0, rotate=90, align=1)

    # Nettoyage du fichier temporaire
    if fontfile and os.path.exists(fontfile):
        try: os.remove(fontfile)
        except: pass

    out.save(output_pdf)
    out.close()
    doc.close()
    if verbose:
        print(f"Couverture générée avec succès → {output_pdf}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python cover_generator.py input.pdf [config.json] [output_cover.pdf]")
        print("")
        print("Comportement intelligent :")
        print("  • Si output.pdf n'est pas précisé → nom automatique : 'fichier - cover.pdf'")
        print("  • Si config.json n'est pas précisé → recherche automatique dans le dossier du PDF ou du script")
        sys.exit(1)

    input_pdf = sys.argv[1]

    # --- Détermination du fichier de sortie ---
    if len(sys.argv) >= 3 and sys.argv[-1].lower().endswith(".pdf") and os.path.basename(sys.argv[-2]) != "config.json":
        # Cas : on a donné explicitement un output.pdf
        output_pdf = sys.argv[-1]
        config_arg_index = 2 if len(sys.argv) == 4 else None
    else:
        # Aucun output donné → on crée "nom du fichier - cover.pdf"
        base_name = Path(input_pdf).stem
        output_pdf = f"{base_name} - cover.pdf"
        config_arg_index = 2 if len(sys.argv) == 3 else None
        print(f"Aucun nom de sortie → généré automatiquement : {output_pdf}")

    # --- Recherche intelligente du config.json ---
    config_path = None

    # Si un argument ressemble à un config.json, on le prend
    if config_arg_index is not None:
        potential_config = sys.argv[config_arg_index]
        if os.path.exists(potential_config):
            config_path = potential_config
            print(f"Config fourni en argument : {config_path}")
        else:
            print(f"Config indiqué introuvable : {potential_config} → recherche automatique")

    # Sinon recherche automatique
    if config_path is None:
        pdf_dir = os.path.dirname(input_pdf) or "."
        script_dir = os.path.dirname(__file__) or "."
        candidates = [
            os.path.join(pdf_dir, "config.json"),
            os.path.join(script_dir, "config.json")
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                config_path = candidate
                print(f"Config trouvé automatiquement : {candidate}")
                break

    if config_path is None:
        print("Aucun config.json trouvé → valeurs par défaut (police Helvetica, tranche 30 mm, titre = nom du fichier)")

    make_cover(input_pdf, config_path, output_pdf, verbose=True)

if __name__ == "__main__":
    main()
