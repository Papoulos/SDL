#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sdl.py

Usage:
python sdl.py "https://www.scribd.com/document/12345678/..." output.pdf

Ce script :
- si l'URL contient '/document/' extrait l'ID numérique et va sur l'URL embed
https://www.scribd.com/embeds/{id}/content
- attend le loader, supprime les éléments de "clutter",
- fait défiler le scroller du document jusqu'en bas (pour forcer le chargement de toutes les pages),
- enregistre la page en PDF.
"""

import re
import time
import argparse
import subprocess
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
from pdf_utils import float_with_comma, crop_pdf, cut_pdf

SCROLL_STEP = 300
SCROLL_DELAY = 0.016 # ~16ms between steps, imite le JS d'origine
MAX_SCROLL_ATTEMPTS = 20000 # garde-fou

def get_embed_url(url: str) -> str:
    """Si URL contient /document/, extrait l'ID et retourne l'URL embed, sinon retourne la même URL."""
    m = re.search(r"/document/(\d+)/", url)
    if m:
        number_id = m.group(1)
        return "https://www.scribd.com/embeds/{}/content".format(number_id)
    return url

def optimize_pdf(filepath: Path):
    """Optimise le fichier PDF en utilisant Ghostscript (ps2pdf)."""
    print("[+] Optimisation du PDF avec Ghostscript...")

    # Charger les paramètres depuis config.json
    pdf_settings = "/prepress"
    try:
        config_path = Path(__file__).parent / "config.json"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                pdf_settings = config.get("pdf_settings", "/prepress")
    except Exception as e:
        print("[!] Erreur lors de la lecture de config.json : {}".format(e))

    temp_output = filepath.with_suffix('.optimized.pdf')

    # Commande : ps2pdf -dPDFSETTINGS=/prepress "input.pdf" "output.pdf"
    # Note : ps2pdf est un wrapper autour de gs
    cmd = [
        "ps2pdf",
        "-dPDFSETTINGS={}".format(pdf_settings),
        str(filepath),
        str(temp_output)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and temp_output.exists():
            # Remplacer le fichier original par le fichier optimisé
            os.replace(temp_output, filepath)
            print("[+] PDF optimisé avec succès.")
        else:
            if "not found" in result.stderr or result.returncode == 127:
                print("[!] Avertissement : Ghostscript (ps2pdf) n'est pas installé. Le fichier n'a pas été optimisé.")
            else:
                print("[!] Échec de l'optimisation par Ghostscript : {}".format(result.stderr))
            if temp_output.exists():
                os.remove(temp_output)
    except FileNotFoundError:
        print("[!] Avertissement : Ghostscript (ps2pdf) n'est pas installé sur le système. Le fichier n'a pas été optimisé.")
    except Exception as e:
        print("[!] Erreur imprévue lors de l'optimisation : {}".format(e))
        if temp_output.exists():
            os.remove(temp_output)

def run(url: str, out_pdf: str, crop_margins: list = None, cut_pages_str: str = None, quality: int = 1, headless: bool = True, optimize: bool = True):
    embed_url = get_embed_url(url)
    print("[+] Using URL: {}".format(embed_url))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            viewport={"width": 1200, "height": 900},
            device_scale_factor=quality
        )
        page = context.new_page()

        try:
            print("[+] Navigating...")
            page.goto(embed_url, timeout=60000) # 60s timeout
        except PWTimeoutError:
            print("[!] Timeout lors du chargement — on continue quand même (la page peut être lente).")

        # Gérer la bannière de cookies
        try:
            print("[+] Recherche de la bannière de cookies...")
            accept_button = page.locator('.osano-cm-accept-all')
            accept_button.click(timeout=5000)
            print("[+] Bannière de cookies acceptée.")
            page.wait_for_timeout(1000) # Petite pause pour que le bandeau disparaisse
        except PWTimeoutError:
            print("[+] Pas de bannière de cookies trouvée ou déjà acceptée.")

        # Fonction JS : suppression des éléments indésirables
        cleanup_js = """
        (() => {
            try {
                document.querySelectorAll('.toolbar_drop, .mobile_overlay').forEach(el => el.remove());
                const commentsSection = document.querySelector('.comments_container');
                if (commentsSection) commentsSection.remove();
            } catch (e) { console.warn('cleanup error', e); }
        })();
        """
        page.evaluate(cleanup_js)

        # Attendre que le scroller apparaisse (ou 10s timeout)
        try:
            print("[+] Waiting for .document_scroller to appear...")
            page.wait_for_selector('.document_scroller', timeout=20000)
        except PWTimeoutError:
            print("[!] .document_scroller introuvable — on va tenter un scroll global de la page.")

        # Si .document_scroller existe, scroll dedans ; sinon scroll de la page entière
        has_scroller = page.query_selector('.document_scroller') is not None

        if has_scroller:
            print("[+] Scrolling inside .document_scroller to force load of all pages...")
            scroll_inner_js = """
            (async () => {{
                const el = document.querySelector('.document_scroller');
                if (!el) return false;
                const step = {};
                const delay = {};
                let last = -1;
                let attempts = 0;
                while ((el.scrollTop + el.clientHeight < el.scrollHeight) && attempts < {}) {{
                    last = el.scrollTop;
                    el.scrollTop = Math.min(el.scrollTop + step, el.scrollHeight);
                    await new Promise(r => setTimeout(r, delay));
                    attempts++;
                    if (el.scrollTop === last) break;
                }}
                el.scrollTop = el.scrollHeight;
                await new Promise(r => setTimeout(r, 200)); // laisser le temps de charger
                document.querySelectorAll('.document_scroller').forEach(x => x.classList.remove('document_scroller'));
                return true;
            }})()
            """.format(SCROLL_STEP, int(SCROLL_DELAY * 1000), MAX_SCROLL_ATTEMPTS)
            try:
                page.evaluate(scroll_inner_js)
            except Exception as e:
                print("[!] Erreur lors du scroll interne : {}".format(e))
        else:
            # fallback : scroll la page entière
            print("[+] Fallback : scroll de la fenêtre (window) pour charger le contenu lazy-loaded...")
            scroll_page_js = """
            (async () => {{
                const step = {};
                const delay = {};
                let last = -1;
                let attempts = 0;
                while ((window.scrollY + window.innerHeight < document.body.scrollHeight) && attempts < {}) {{
                    last = window.scrollY;
                    window.scrollBy(0, step);
                    await new Promise(r => setTimeout(r, delay));
                    attempts++;
                    if (window.scrollY === last) break;
                }}
                window.scrollTo(0, document.body.scrollHeight);
                await new Promise(r => setTimeout(r, 500));
                return true;
            }})()
            """.format(SCROLL_STEP, int(SCROLL_DELAY * 1000), MAX_SCROLL_ATTEMPTS)
            try:
                page.evaluate(scroll_page_js)
            except Exception as e:
                print("[!] Erreur lors du scroll global : {}".format(e))

        # Un dernier nettoyage avant impression (retirer overflow:hidden potentiels)
        final_cleanup = """
        (() => {
            try {
                document.body.style.overflow = 'visible';
                document.documentElement.style.overflow = 'visible';
                document.querySelectorAll('.toolbar_drop, .mobile_overlay').forEach(el => el.remove());
                document.querySelectorAll('.document_scroller').forEach(el => el.classList.remove('document_scroller'));
            } catch (e) { console.warn('final cleanup', e); }
        })();
        """
        page.evaluate(final_cleanup)

        # Attendre quelques instants pour s'assurer que tout est chargé
        print("[+] Attente finale pour le chargement des pages...")
        time.sleep(1.0 + 0.01 * SCROLL_STEP)

        # Génération PDF
        print("[+] Génération du PDF en mémoire...")
        try:
            pdf_data = page.pdf(
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "10mm", "bottom": "10mm", "left": "8mm", "right": "8mm"}
            )
            print("[+] PDF généré avec succès en mémoire.")

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

            if optimize:
                optimize_pdf(out_path)

        except Exception as e:
            print("[!] Échec de la génération ou sauvegarde du PDF : {}".format(e))

        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Télécharge un document depuis Scribd et le convertit en PDF.',
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Exemples d'utilisation:
  # Téléchargement simple avec nom de fichier spécifié
  python3 sdl.py "https://www.scribd.com/document/123456/Mon-Doc" sortie.pdf

  # Téléchargement avec nom de fichier automatique (le PDF sera nommé 'Mon-Doc.pdf')
  python3 sdl.py "https://www.scribd.com/document/123456/Mon-Doc"

  # Rognage des marges (1cm en haut, 2cm en bas, 1.5cm à gauche, 1.5cm à droite)
  # Note: accepte les virgules et les points comme séparateurs décimaux.
  python3 sdl.py "url_du_document" mon_fichier.pdf --crop 1 2 1,5 1.5
"""
    )
    parser.add_argument('url', metavar='URL', help="L'URL du document Scribd à télécharger.")
    parser.add_argument('output_pdf', metavar='FICHIER_SORTIE', nargs='?', default=None, help='Le chemin du fichier PDF de sortie (optionnel).\nSi non fourni, le nom est dérivé du dernier segment de l\'URL.')
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
    parser.add_argument(
        '--quality',
        type=int,
        default=1,
        metavar='FACTEUR',
        help="""Facteur de qualité (résolution) pour le rendu du PDF.
Utilisez 2 pour une qualité 'Retina' (double résolution).
La valeur par défaut est 1 (qualité normale)."""
    )
    parser.add_argument(
        '-no-optimize', '--no-optimize',
        action='store_false',
        dest='optimize',
        help="Ne pas optimiser le PDF final avec Ghostscript."
    )
    parser.set_defaults(optimize=True)
    args = parser.parse_args()

    output_pdf = args.output_pdf
    if output_pdf is None:
        # Generate filename from URL if not provided
        url_for_name = args.url.split('?')[0].rstrip('/')
        filename_base = url_for_name.split('/')[-1]

        # If the name is empty or looks like a domain, fallback
        if not filename_base or filename_base in ['www.scribd.com', 'scribd.com']:
            match_id = re.search(r"/document/(\d+)", args.url)
            if match_id:
                filename_base = match_id.group(1)  # Use document ID as fallback
            else:
                filename_base = "document"  # Final fallback

        output_pdf = "{}.pdf".format(filename_base)
        print("[+] Nom de fichier non fourni. Utilisation auto : {}".format(output_pdf))

    run(args.url, output_pdf, crop_margins=args.crop, cut_pages_str=args.cut, quality=args.quality, headless=True, optimize=args.optimize)
