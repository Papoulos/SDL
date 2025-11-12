#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_utils.py

Shared utility functions for PDF manipulation.
"""

import io
import argparse
from pypdf import PdfReader, PdfWriter

def float_with_comma(value: str) -> float:
    """Converts a string with comma or period as decimal separator to float."""
    try:
        return float(value.replace(',', '.'))
    except ValueError:
        raise argparse.ArgumentTypeError("'{}' is not a valid floating-point number.".format(value))

def crop_pdf(pdf_data: bytes, crop_margins: list) -> bytes:
    """Crops the pages of a PDF according to specified margins."""
    cm_to_points = 72 / 2.54
    margin_top = crop_margins[0] * cm_to_points
    margin_bottom = crop_margins[1] * cm_to_points
    margin_left = crop_margins[2] * cm_to_points
    margin_right = crop_margins[3] * cm_to_points

    try:
        reader = PdfReader(io.BytesIO(pdf_data))
        writer = PdfWriter()

        for page in reader.pages:
            page.mediabox.lower_left = (
                page.mediabox.left + margin_left,
                page.mediabox.bottom + margin_bottom
            )
            page.mediabox.upper_right = (
                page.mediabox.right - margin_right,
                page.mediabox.top - margin_top
            )
            writer.add_page(page)

        cropped_pdf_stream = io.BytesIO()
        writer.write(cropped_pdf_stream)
        print("[+] PDF rogné avec succès.")
        return cropped_pdf_stream.getvalue()

    except Exception as e:
        print("[!] Échec du rognage PDF : {}".format(e))
        return pdf_data

def cut_pdf(pdf_data: bytes, pages_to_remove_str: str) -> bytes:
    """
    Supprime des pages spécifiques d'un PDF en se basant sur une chaîne de caractères.
    Exemples pour pages_to_remove_str: '5', '1-3', '1,5,10-12'.
    """
    def parse_pages_to_remove(pages_str: str) -> set:
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
                        start, end = end, start
                    pages_to_remove.update(range(start, end + 1))
                except ValueError:
                    print("[!] Avertissement : intervalle de pages invalide ignoré : '{}'".format(part))
            else:
                try:
                    pages_to_remove.add(int(part))
                except ValueError:
                    print("[!] Avertissement : numéro de page invalide ignoré : '{}'".format(part))
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
            page_number = i + 1
            if page_number not in pages_to_cut:
                writer.add_page(page)
                pages_kept_count += 1

        if pages_kept_count == num_pages_original:
            print("[+] Aucune des pages spécifiées n'a été trouvée dans le document.")
            return pdf_data

        cut_pdf_stream = io.BytesIO()
        writer.write(cut_pdf_stream)
        print("[+] PDF modifié avec succès. {} page(s) supprimée(s).".format(num_pages_original - pages_kept_count))
        return cut_pdf_stream.getvalue()

    except Exception as e:
        print("[!] Échec de la suppression de pages : {}".format(e))
        return pdf_data
