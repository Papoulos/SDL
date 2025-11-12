#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crop.py

Usage:
python crop.py input.pdf HAUT BAS GAUCHE DROITE [output.pdf]

Ce script permet de rogner un fichier PDF existant en spécifiant les marges.
"""

import argparse
import io
from typing import List
from pypdf import PdfReader, PdfWriter


def float_with_comma(value: str) -> float:
    """Converts a string with comma or period as decimal separator to float."""
    try:
        return float(value.replace(',', '.'))
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"'{value}' is not a valid floating-point number."
        )


def crop_pdf(pdf_data: bytes, crop_margins: List[float]) -> bytes:
    """Crops the pages of a PDF according to specified margins."""
    # Conversion factor from cm to points (1 inch = 72 points, 1 inch = 2.54 cm)
    cm_to_points = 72 / 2.54

    # Margins to remove, in points
    margin_top = crop_margins[0] * cm_to_points
    margin_bottom = crop_margins[1] * cm_to_points
    margin_left = crop_margins[2] * cm_to_points
    margin_right = crop_margins[3] * cm_to_points

    try:
        reader = PdfReader(io.BytesIO(pdf_data))
        writer = PdfWriter()

        for page in reader.pages:
            # Adjust the media box to crop the page
            page.mediabox.lower_left = (
                page.mediabox.left + margin_left,
                page.mediabox.bottom + margin_bottom
            )
            page.mediabox.upper_right = (
                page.mediabox.right - margin_right,
                page.mediabox.top - margin_top
            )
            writer.add_page(page)

        # Write the cropped PDF to a byte stream
        cropped_pdf_stream = io.BytesIO()
        writer.write(cropped_pdf_stream)

        print("[+] PDF rogné avec succès.")
        return cropped_pdf_stream.getvalue()

    except Exception as e:
        print(f"[!] Échec du rognage PDF : {e}")
        # Return original data if cropping fails
        return pdf_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Rogner les pages d\'un fichier PDF existant.',
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Exemple d'utilisation:
  # Rognage avec 1cm en haut, 2cm en bas, 1.5cm à gauche, 1.5cm à droite
  python3 crop.py mon_fichier.pdf 1 2 1,5 1.5

  # Spécifier un fichier de sortie différent
  python3 crop.py mon_fichier.pdf 1 1 1 1 rogné.pdf
"""
    )
    parser.add_argument('input_pdf', metavar='FICHIER_ENTRÉE', help="Le chemin du fichier PDF à rogner.")
    parser.add_argument(
        'crop_margins',
        nargs=4,
        type=float_with_comma,
        metavar=('HAUT', 'BAS', 'GAUCHE', 'DROITE'),
        help="""Les quatre valeurs de rognage en cm:
  HAUT   : marge à supprimer en haut
  BAS    : marge à supprimer en bas
  GAUCHE : marge à supprimer à gauche
  DROITE : marge à supprimer à droite
Accepte les nombres à virgule (ex: 1,5) ou à point (ex: 2.5)."""
    )
    parser.add_argument('output_pdf', metavar='FICHIER_SORTIE', nargs='?', default=None, help='Le chemin du fichier PDF de sortie (optionnel).\nPar défaut, "_cropped" est ajouté au nom du fichier d\'entrée.')
    args = parser.parse_args()

    # Déterminer le nom du fichier de sortie
    output_pdf = args.output_pdf
    if output_pdf is None:
        input_path = args.input_pdf
        # Insère "_cropped" avant l'extension .pdf
        if input_path.lower().endswith('.pdf'):
            output_pdf = input_path[:-4] + '_cropped.pdf'
        else:
            output_pdf = input_path + '_cropped.pdf'
        print(f"[+] Nom de fichier de sortie non fourni. Utilisation auto : {output_pdf}")

    try:
        # Lire le fichier PDF d'entrée
        with open(args.input_pdf, 'rb') as f:
            pdf_data = f.read()

        # Rogner le PDF
        cropped_data = crop_pdf(pdf_data, args.crop_margins)

        # Sauvegarder le PDF rogné
        with open(output_pdf, 'wb') as f:
            f.write(cropped_data)

        print(f"[+] PDF rogné et sauvegardé dans : {output_pdf}")

    except FileNotFoundError:
        print(f"[!] Erreur : Le fichier d'entrée '{args.input_pdf}' n'a pas été trouvé.")
    except Exception as e:
        print(f"[!] Une erreur inattendue est survenue : {e}")
