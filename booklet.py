#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
booklet.py

Un outil d'imposition pour créer des carnets pliés à partir d'un fichier PDF.
"""

import argparse
import sys
import math
import pikepdf
from pikepdf import Rectangle

def taille_carnet_type(value):
    """Vérifie que la taille du carnet est un entier multiple de 4."""
    try:
        ivalue = int(value)
        if ivalue <= 0 or ivalue % 4 != 0:
            raise argparse.ArgumentTypeError(
                "la valeur doit être un entier positif multiple de 4."
            )
        return ivalue
    except ValueError:
        raise argparse.ArgumentTypeError("la valeur doit être un entier.")

def placer_page(page_cible, page_source, pdf_dest, tx, ty, scale):
    """
    Place une page source sur une page cible en ajoutant un nouveau flux de contenu
    avec les transformations (échelle, translation) nécessaires.
    """
    form_xobject = page_source.as_form_xobject()
    resource_name = page_cible.add_resource(form_xobject, '/XObject')

    matrix = pikepdf.Matrix().scaled(scale, scale).translated(tx, ty)
    matrix_str = f'{matrix.a:.4f} {matrix.b:.4f} {matrix.c:.4f} {matrix.d:.4f} {matrix.e:.4f} {matrix.f:.4f}'

    command = b"q\n%b cm\n%b Do\nQ\n" % (
        matrix_str.encode('ascii'),
        bytes(resource_name)
    )

    new_stream = pikepdf.Stream(pdf_dest, data=command)

    if pikepdf.Name.Contents not in page_cible:
        page_cible.Contents = new_stream
    else:
        existing_contents = page_cible.Contents
        if isinstance(existing_contents, pikepdf.Array):
            existing_contents.append(new_stream)
        else:
            page_cible.Contents = pikepdf.Array([existing_contents, new_stream])

def main():
    """Fonction principale du script."""
    parser = argparse.ArgumentParser(
        description="Crée un PDF imposé pour l'impression de carnets.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument("fichier_entree", help="Le chemin vers le PDF source.")
    parser.add_argument("fichier_sortie", help="Le chemin vers le PDF final qui sera créé.")
    parser.add_argument("--taille-carnet", type=taille_carnet_type, default=16, help="Nombre de pages par carnet (doit être un multiple de 4).\nDéfaut : 16")
    parser.add_argument("--format-source", choices=["A4", "A5"], default="A5", help="Format des pages sources.\nA4: Implique une réduction A4 -> A5.\nA5: Imposition directe.\nDéfaut : A5")
    parser.add_argument("--gutter", type=float, default=0, help="Espace central total (en mm) pour la pliure.\nDéfaut : 0")
    parser.add_argument("--creep", type=float, default=0, help="Compensation (en mm) de la poussée (chasse de papier).\nDéfaut : 0")

    args = parser.parse_args()

    print("--- Paramètres d'imposition ---")
    print(u"Fichier d'entrée : {}".format(args.fichier_entree))
    print(u"Fichier de sortie : {}".format(args.fichier_sortie))
    print(u"Taille des carnets : {} pages".format(args.taille_carnet))
    print(u"Format source : {}".format(args.format_source))
    print(u"Gouttière (gutter) : {} mm".format(args.gutter))
    print(u"Compensation (creep) : {} mm".format(args.creep))
    print("-------------------------------")

    try:
        source_pdf = pikepdf.open(args.fichier_entree)
    except FileNotFoundError:
        print(u"Erreur : Le fichier d'entrée '{}' n'a pas été trouvé.".format(args.fichier_entree))
        sys.exit(1)
    except pikepdf.PdfError as e:
        print(u"Erreur à l'ouverture du PDF '{}': {}".format(args.fichier_entree, e))
        sys.exit(1)

    num_pages = len(source_pdf.pages)
    print(u"Nombre de pages initial : {}".format(num_pages))

    # 1. Rembourrage (Padding) pour atteindre un multiple de 4
    if num_pages == 0:
        print("Le PDF d'entrée est vide. Rien à faire.")
        sys.exit(0)

    pages_to_add = 0
    if num_pages % 4 != 0:
        pages_to_add = 4 - (num_pages % 4)

    if pages_to_add > 0:
        print(u"Ajout de {} pages blanches avant la dernière page pour atteindre un multiple de 4.".format(pages_to_add))

        last_page_content = source_pdf.pages[-1]
        page_box = last_page_content.mediabox
        page_size = (page_box[2] - page_box[0], page_box[3] - page_box[1])

        # Supprimer la dernière page temporairement
        del source_pdf.pages[-1]

        # Ajouter les pages blanches
        for _ in range(pages_to_add):
            source_pdf.add_blank_page(page_size=page_size)

        # Rajouter la dernière page à la fin
        source_pdf.pages.append(last_page_content)

        print(u"Nombre de pages après ajout : {}".format(len(source_pdf.pages)))

    # 2. Imposition
    print("Début de l'imposition...")
    final_pdf = pikepdf.new()

    mm_to_pt = 72 / 25.4
    A4_PAYSAGE_SIZE = (297 * mm_to_pt, 210 * mm_to_pt)
    A5_PORTRAIT_SIZE = (148 * mm_to_pt, 210 * mm_to_pt)
    A4_PORTRAIT_SIZE = (210 * mm_to_pt, 297 * mm_to_pt)

    scale = A5_PORTRAIT_SIZE[0] / A4_PORTRAIT_SIZE[0] if args.format_source == 'A4' else 1.0

    taille_carnet_max = args.taille_carnet

    processed_pages = 0
    carnet_num = 0
    while processed_pages < len(source_pdf.pages):
        carnet_num += 1

        start_idx = processed_pages
        # Détermine la taille du carnet courant (peut être plus petit pour le dernier)
        taille_carnet_courant = min(taille_carnet_max, len(source_pdf.pages) - start_idx)

        print(u"Traitement du carnet {} ({} pages)...".format(carnet_num, taille_carnet_courant))

        carnet_pages = source_pdf.pages[start_idx : start_idx + taille_carnet_courant]

        for j in range(taille_carnet_courant // 4):
            p_droite_recto_idx = 2 * j
            p_gauche_verso_idx = p_droite_recto_idx + 1
            p_droite_verso_idx = (taille_carnet_courant - 1) - (2 * j) - 1
            p_gauche_recto_idx = p_droite_verso_idx + 1

            page_gauche_recto = carnet_pages[p_gauche_recto_idx]
            page_droite_recto = carnet_pages[p_droite_recto_idx]
            page_gauche_verso = carnet_pages[p_gauche_verso_idx]
            page_droite_verso = carnet_pages[p_droite_verso_idx]

            # --- Calcul des décalages (Gutter & Creep) ---

            # Gutter: pousse le contenu vers l'extérieur pour la reliure
            gutter_offset = args.gutter * mm_to_pt / 2

            # Creep: pousse les pages intérieures plus vers l'extérieur que les extérieures
            # pour compenser l'épaisseur du papier. Il est nul pour la feuille extérieure
            # et maximal pour la feuille centrale.
            nombre_feuilles = taille_carnet_courant / 4
            # La "profondeur" de la feuille dans le carnet (0 pour l'extérieure, augmente vers le centre)
            profondeur = min(j, nombre_feuilles - 1 - j)
            # Le creep_offset est proportionnel à la profondeur.
            # On normalise par la profondeur maximale possible pour une linéarité parfaite.
            profondeur_max = math.floor((nombre_feuilles - 1) / 2)
            max_creep_par_page = args.creep * mm_to_pt / 2
            creep_offset = (profondeur / profondeur_max) * max_creep_par_page if profondeur_max > 0 else 0

            page_recto = final_pdf.add_blank_page(page_size=A4_PAYSAGE_SIZE)
            page_verso = final_pdf.add_blank_page(page_size=A4_PAYSAGE_SIZE)

            # Le décalage total est la somme des deux effets.
            # Gutter: pousse vers l'extérieur. Gauche -> négatif, Droite -> positif
            # Creep: pousse vers l'extérieur. Gauche -> négatif, Droite -> positif

            offset_gauche = -gutter_offset - creep_offset
            offset_droite = gutter_offset + creep_offset

            # Ordre corrigé : placer la page de gauche AVANT la page de droite
            placer_page(page_recto, page_gauche_recto, final_pdf, offset_gauche, 0, scale)
            placer_page(page_recto, page_droite_recto, final_pdf, A5_PORTRAIT_SIZE[0] + offset_droite, 0, scale)

            placer_page(page_verso, page_gauche_verso, final_pdf, offset_gauche, 0, scale)
            placer_page(page_verso, page_droite_verso, final_pdf, A5_PORTRAIT_SIZE[0] + offset_droite, 0, scale)

        processed_pages += taille_carnet_courant

    try:
        final_pdf.save(args.fichier_sortie)
        print(u"Imposition terminée avec succès.")
        print(u"Fichier de sortie créé : {}".format(args.fichier_sortie))
    except Exception as e:
        print(u"Erreur lors de la sauvegarde du fichier de sortie : {}".format(e))
        sys.exit(1)

if __name__ == "__main__":
    main()
