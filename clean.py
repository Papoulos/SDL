#!/usr/bin/env python3
"""
clean.py

Usage:
python clean.py input.pdf [output.pdf] --crop <margins> --cut <pages>

Ce script permet de manipuler un fichier PDF local pour :
- Rogner les marges.
- Supprimer des pages spécifiques.
"""

import argparse
import io
from pathlib import Path
from typing import List
from pypdf import PdfReader, PdfWriter

def float_with_comma(value: str) -> float:
    """Converts a string with comma or period as decimal separator to float."""
    try:
        return float(value.replace(',', '.'))
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a valid floating-point number.")

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

def cut_pdf(pdf_data: bytes, pages_to_remove_str: str) -> bytes:
    """
    Supprime des pages spécifiques d'un PDF en se basant sur une chaîne de caractères.
    Exemples pour pages_to_remove_str: '5', '1-3', '1,5,10-12'.
    """
    def parse_pages_to_remove(pages_str: str) -> set[int]:
        """Analyse une chaîne comme '1,3,5-7' en un ensemble de numéros de page."""
        pages_to_remove = set()
        if not pages_str:
            return pages_to_remove

        parts = pages_str.split(',')
        for part in parts:
            part = part.strip()
            if '-' in part:
                try:
                    start, end = map(int, part.split('-'))
                    if start > end:
                        start, end = end, start # Inverser si l'ordre est incorrect
                    pages_to_remove.update(range(start, end + 1))
                except ValueError:
                    print(f"[!] Avertissement : intervalle de pages invalide ignoré : '{part}'")
            else:
                try:
                    pages_to_remove.add(int(part))
                except ValueError:
                    print(f"[!] Avertissement : numéro de page invalide ignoré : '{part}'")
        return pages_to_remove

    pages_to_cut = parse_pages_to_remove(pages_to_remove_str)
    if not pages_to_cut:
        print("[+] Aucune page valide à supprimer spécifiée.")
        return pdf_data

    try:
        reader = PdfReader(io.BytesIO(pdf_data))
        writer = PdfWriter()

        num_pages_original = len(reader.pages)
        pages_kept_count = 0

        for i, page in enumerate(reader.pages):
            # Les numéros de page sont 1-indexés pour l'utilisateur
            page_number = i + 1
            if page_number not in pages_to_cut:
                writer.add_page(page)
                pages_kept_count += 1

        if pages_kept_count == num_pages_original:
            print("[+] Aucune des pages spécifiées n'a été trouvée dans le document.")
            return pdf_data

        # Écrire le PDF modifié dans un flux d'octets
        cut_pdf_stream = io.BytesIO()
        writer.write(cut_pdf_stream)

        print(f"[+] PDF modifié avec succès. {num_pages_original - pages_kept_count} page(s) supprimée(s).")
        return cut_pdf_stream.getvalue()

    except Exception as e:
        print(f"[!] Échec de la suppression de pages : {e}")
        # Retourner les données originales si la suppression échoue
        return pdf_data

def run(input_pdf: str, out_pdf: str, crop_margins: List[float] = None, cut_pages_str: str = None):
    try:
        in_path = Path(input_pdf)
        if not in_path.is_file():
            print(f"[!] Le fichier d'entrée n'existe pas : {input_pdf}")
            return

        print(f"[+] Lecture du fichier : {in_path.resolve()}")
        pdf_data = in_path.read_bytes()

        if crop_margins:
            print("[+] Rognage du PDF...")
            pdf_data = crop_pdf(pdf_data, crop_margins)

        if cut_pages_str:
            print("[+] Suppression de pages...")
            pdf_data = cut_pdf(pdf_data, cut_pages_str)

        out_path = Path(out_pdf)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'wb') as f:
            f.write(pdf_data)

        print(f"[+] PDF sauvegardé dans : {out_path.resolve()}")

    except Exception as e:
        print(f"[!] Une erreur est survenue : {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Modifie un fichier PDF local en rognant les marges ou en supprimant des pages.',
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Exemples d'utilisation:
  # Rogner les marges (1cm en haut, 2cm en bas, 1.5cm à gauche, 1.5cm à droite)
  python3 clean.py mon_fichier.pdf sortie.pdf --crop 1 2 1,5 1.5

  # Supprimer les pages 1 et 5 à 7
  python3 clean.py mon_fichier.pdf sortie.pdf --cut 1,5-7

  # Combiner les deux opérations
  python3 clean.py in.pdf out.pdf --crop 1 1 1 1 --cut 1

  # Utiliser un nom de sortie automatique ('mon_fichier-cleaned.pdf')
  python3 clean.py mon_fichier.pdf --cut 1
"""
    )
    parser.add_argument('input_pdf', metavar='FICHIER_ENTREE', help="Le chemin du fichier PDF à modifier.")
    parser.add_argument('output_pdf', metavar='FICHIER_SORTIE', nargs='?', default=None, help='Le chemin du fichier PDF de sortie (optionnel).\nSi non fourni, le nom est dérivé du nom d'entrée (ex: "fichier-cleaned.pdf").')
    parser.add_argument(
        '--crop',
        nargs=4,
        type=float_with_comma,
        metavar=('HAUT', 'BAS', 'GAUCHE', 'DROITE'),
        help="""Rogner le PDF en supprimant les marges (en cm).
Les quatre valeurs correspondent aux marges à supprimer:
  HAUT   : marge supérieure
  BAS    : marge inférieure
  GAUCHE : marge de gauche
  DROITE : marge de droite
Accepte les nombres à virgule (ex: 1,5) ou à point (ex: 2.5)."""
    )
    parser.add_argument(
        '--cut',
        type=str,
        metavar='PAGES',
        help="""Supprimer des pages spécifiques du PDF final.
Les pages peuvent être spécifiées individuellement ou par intervalle:
  '5'      : supprime la page 5
  '1-3'    : supprime les pages 1, 2 et 3
  '1,5,10-12': supprime les pages 1, 5, 10, 11 et 12"""
    )
    args = parser.parse_args()

    output_pdf = args.output_pdf
    if output_pdf is None:
        # Generate filename from input path if not provided
        in_path = Path(args.input_pdf)
        output_pdf = f"{in_path.stem}-cleaned{in_path.suffix}"
        print(f"[+] Nom de fichier non fourni. Utilisation auto : {output_pdf}")

    # Vérifier si l'entrée et la sortie sont identiques
    if Path(args.input_pdf).resolve() == Path(output_pdf).resolve():
        print("[!] Erreur : Le fichier d'entrée et de sortie ne peuvent pas être identiques.")
    else:
        run(args.input_pdf, output_pdf, crop_margins=args.crop, cut_pages_str=args.cut)
