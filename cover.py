#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cover_generator_fixed.py
Correction : Enregistrement explicite de la police via insert_font pour garantir son affichage.
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
    # Gestion des liens GitHub raw pour éviter les erreurs de téléchargement HTML
    if "github.com" in url and "blob" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    fd, path = tempfile.mkstemp(suffix=".ttf")
    os.close(fd)
    try:
        urllib.request.urlretrieve(url, path)
        return path
    except Exception as e:
        print(f"Erreur téléchargement font: {e}")
        return None

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
    # FRONT
    # ===================================================================
    page_front = out.new_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
    outer_w_f = a5_w_pt + mm2pt(LEFT_MARGIN_FRONT_MM + OTHER_MARGINS_MM)
    outer_h   = a5_h_pt + mm2pt(OTHER_MARGINS_MM * 2)
    outer_front = fitz.Rect((A4_WIDTH_PT - outer_w_f)/2, (A4_HEIGHT_PT - outer_h)/2,
                            (A4_WIDTH_PT - outer_w_f)/2 + outer_w_f, (A4_HEIGHT_PT - outer_h)/2 + outer_h)
    inner_front = outer_front + (mm2pt(LEFT_MARGIN_FRONT_MM), mm2pt(OTHER_MARGINS_MM),
                                 -mm2pt(OTHER_MARGINS_MM), -mm2pt(OTHER_MARGINS_MM))
    page_front.draw_rect(outer_front, color=(0,0,0), width=1.5)
    place_page_scaled_center(page_front, doc, 0, inner_front)

    # ===================================================================
    # BACK
    # ===================================================================
    page_back = out.new_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
    outer_w_b = a5_w_pt + mm2pt(RIGHT_MARGIN_BACK_MM + OTHER_MARGINS_MM)
    outer_back = fitz.Rect((A4_WIDTH_PT - outer_w_b)/2, (A4_HEIGHT_PT - outer_h)/2,
                           (A4_WIDTH_PT - outer_w_b)/2 + outer_w_b, (A4_HEIGHT_PT - outer_h)/2 + outer_h)
    inner_back = outer_back + (mm2pt(OTHER_MARGINS_MM), mm2pt(OTHER_MARGINS_MM),
                               -mm2pt(RIGHT_MARGIN_BACK_MM), -mm2pt(OTHER_MARGINS_MM))
    page_back.draw_rect(outer_back, color=(0,0,0), width=1.5)
    place_page_scaled_center(page_back, doc, doc.page_count-1, inner_back)

    # ===================================================================
    # SPINE (Tranche) - CORRIGÉ
    # ===================================================================
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

    # 1. Gestion de la police
    fontfile = None
    fontname_to_use = "helv"  # Par défaut Helvetica

    if font_url:
        fontfile = download_font(font_url)
        if fontfile:
            try:
                # --- CORRECTION MAJEURE ICI ---
                # On enregistre explicitement la police sur la page
                # On lui donne le nom interne "customfont"
                page_spine.insert_font(fontname="customfont", fontfile=fontfile)
                fontname_to_use = "customfont"
                if verbose:
                    print(f"Police enregistrée avec succès sous le nom '{fontname_to_use}' depuis {fontfile}")
            except Exception as e:
                print("Erreur lors de l'enregistrement de la police (insert_font) :", e)
                fontname_to_use = "helv"
        else:
            if verbose: print("Impossible de télécharger la police, utilisation de Helvetica.")

    # 2. Texte de la tranche
    text = spine_text or Path(input_pdf).stem
    
    # Zone d'écriture avec padding
    padding = mm2pt(7)
    text_rect = spine_rect + (padding, padding, -padding, -padding)
    
    # Taille de départ
    fontsize = text_rect.height * 0.77

    # 3. Boucle d'ajustement de la taille
    success = False
    for i in range(50):
        try:
            # On utilise maintenant 'fontname' au lieu de 'fontfile' dans insert_textbox
            rc = page_spine.insert_textbox(
                text_rect,
                text,
                fontsize=fontsize,
                fontname=fontname_to_use,  # Utilisation du nom enregistré
                align=fitz.TEXT_ALIGN_CENTER,
                rotate=90,
                color=0
            )
            if rc >= 0:  # rc < 0 signifie que le texte n'a pas tenu
                success = True
                if verbose: print(f"Texte inséré avec succès (taille {fontsize:.2f})")
                break
        except Exception as e:
            # Si erreur critique, on arrête
            print(f"Erreur insert_textbox: {e}")
            break
            
        # Si ça ne rentre pas, on réduit
        fontsize *= 0.93
        # Nettoyage pour la prochaine tentative (PyMuPDF conserve parfois l'état partiel)
        # Mais ici comme on réécrit par dessus ou que ça échoue, pas besoin de 'clean' lourd.

    if not success:
        if verbose: print("Échec placement texte principal, tentative fallback.")
        # Secours absolu Helvetica petit
        try:
            page_spine.insert_textbox(text_rect, text, fontsize=12, fontname="helv", color=0, rotate=90, align=1)
        except:
            pass

    # Nettoyage fichier temporaire
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
        print("Usage: python cover_generator.py input.pdf [config.json] [output_cover.pdf]")
        sys.exit(1)

    input_pdf = sys.argv[1]

    # --- Détermination sortie ---
    if len(sys.argv) >= 3 and sys.argv[-1].lower().endswith(".pdf") and os.path.basename(sys.argv[-2]) != "config.json":
        output_pdf = sys.argv[-1]
        config_arg_index = 2 if len(sys.argv) == 4 else None
    else:
        base_name = Path(input_pdf).stem
        output_pdf = f"{base_name} - Cover.pdf"
        config_arg_index = 2 if len(sys.argv) == 3 else None
        print(f"Sortie auto : {output_pdf}")

    # --- Recherche Config ---
    config_path = None
    if config_arg_index is not None:
        potential_config = sys.argv[config_arg_index]
        if os.path.exists(potential_config):
            config_path = potential_config
        else:
            print(f"Config introuvable : {potential_config}")

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
                print(f"Config trouvé : {candidate}")
                break

    make_cover(input_pdf, config_path, output_pdf, verbose=True)

if __name__ == "__main__":
    main()
