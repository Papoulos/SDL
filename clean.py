#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clean.py

Usage:
python clean.py input.pdf [output.pdf] --crop <margins> --cut <pages>

Ce script permet de manipuler un fichier PDF local pour :
- Rogner les marges.
- Supprimer des pages spécifiques.
"""

import argparse
from pathlib import Path
from pdf_utils import float_with_comma, crop_pdf, cut_pdf

def run(input_pdf: str, out_pdf: str, crop_margins: list = None, cut_pages_str: str = None):
    try:
        in_path = Path(input_pdf)
        if not in_path.is_file():
            print("[!] Le fichier d'entrée n'existe pas : {}".format(input_pdf))
            return

        print("[+] Lecture du fichier : {}".format(in_path.resolve()))
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

        print("[+] PDF sauvegardé dans : {}".format(out_path.resolve()))

    except Exception as e:
        print("[!] Une erreur est survenue : {}".format(e))

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
    parser.add_argument('output_pdf', metavar='FICHIER_SORTIE', nargs='?', default=None, help='Le chemin du fichier PDF de sortie (optionnel).\nSi non fourni, le nom est dérivé du nom d\'entrée (ex: "fichier-cleaned.pdf").')
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
        in_path = Path(args.input_pdf)
        output_pdf = "{}-cleaned{}".format(in_path.stem, in_path.suffix)
        print("[+] Nom de fichier non fourni. Utilisation auto : {}".format(output_pdf))

    if Path(args.input_pdf).resolve() == Path(output_pdf).resolve():
        print("[!] Erreur : Le fichier d'entrée et de sortie ne peuvent pas être identiques.")
    else:
        run(args.input_pdf, output_pdf, crop_margins=args.crop, cut_pages_str=args.cut)
