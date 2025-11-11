"""
A script to download documents from Scribd.com as PDF files.
This script uses selenium and a headless Chrome browser to render the document
and then prints it to a PDF file.
"""
import argparse
import logging
import time
import re
import base64
import os
import io

from pypdf import PdfReader, PdfWriter
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def float_with_comma(value):
    """Converts a string with comma or period as decimal separator to float."""
    try:
        return float(value.replace(',', '.'))
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a valid floating-point number.")

def setup_driver():
    """Sets up the headless Chrome WebDriver."""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('accept-language=en-US,en;q=0.9')
    options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    options.add_experimental_option('prefs', {
        'printing.print_to_pdf': True,
    })
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    stealth(driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
            )

    return driver

def sanitize_filename(filename):
    """Sanitizes a string to be used as a valid filename."""
    sanitized = re.sub(r'[\\/*?:"<>|]', "", filename)
    return sanitized.replace(' ', '_')


def crop_pdf(pdf_data, crop_margins):
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

        logging.info("PDF cropped successfully.")
        return cropped_pdf_stream.getvalue()

    except Exception as e:
        logging.error(f"Failed to crop PDF: {e}")
        # Return original data if cropping fails
        return pdf_data


def download_document_as_pdf(driver, url, original_url, crop_margins=None, timeout=300):
    """Navigates to the URL and saves the document as a PDF."""
    try:
        logging.info(f"Navigating to: {url}")
        driver.get(url)

        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".document_scroller"))
        )
        logging.info("Document page loaded successfully.")

        try:
            logging.info("Attempting to click 'Accept All' on cookie banner...")
            accept_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".osano-cm-accept-all"))
            )
            accept_button.click()
            logging.info("Successfully clicked 'Accept All'.")
        except TimeoutException:
            logging.info("Cookie banner not found or already accepted, proceeding.")

        # Set the script timeout to 2 minutes
        driver.set_script_timeout(timeout)

        # Execute JavaScript to prepare the page for printing
        logging.info("Executing JavaScript to prepare the page...")
        driver.execute_async_script("""
            const done = arguments[arguments.length - 1];

            // Remove clutter
            document.querySelectorAll('.toolbar_drop, .mobile_overlay').forEach(el => el.remove());
            const commentsSection = document.querySelector('.comments_container');
            if (commentsSection) {
                commentsSection.remove();
            }

            // Scroll to bottom to load all content
            const scroller = document.querySelector('.document_scroller');
            if (scroller) {
                const scrollStep = 300;
                const scrollInterval = 16;
                const intervalId = setInterval(() => {
                    const lastScrollTop = scroller.scrollTop;
                    scroller.scrollTop += scrollStep;

                    if (scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight || scroller.scrollTop === lastScrollTop) {
                        scroller.scrollTop = scroller.scrollHeight;
                        clearInterval(intervalId);
                        done();
                    }
                }, scrollInterval);
            } else {
                done();
            }
        """)

        driver.execute_script("document.querySelectorAll('.document_scroller').forEach(el => el.classList.remove('document_scroller'));")
        logging.info("Page preparation complete.")

        logging.info("Generating PDF...")
        print_to_pdf_result = driver.execute_cdp_cmd(
            "Page.printToPDF", {
                "printBackground": True,
                "format": "A4",
                "landscape": False,
                "scale": 1
            })

        pdf_data = base64.b64decode(print_to_pdf_result['data'])

        # Crop the PDF if crop margins are provided
        if crop_margins:
            logging.info("Cropping the PDF...")
            pdf_data = crop_pdf(pdf_data, crop_margins)

        # Sanitize title for filename
        # Extract the last part of the URL to use as a filename
        filename_from_url = original_url.rstrip('/').split('/')[-1]

        # If the extracted part is just a number (like in '/document/12345'),
        # fall back to using the document title.
        if filename_from_url.isdigit():
            title = driver.title
            filename = sanitize_filename(title) + ".pdf"
        else:
            filename = sanitize_filename(filename_from_url) + ".pdf"


        # Ensure filename is not empty
        if not filename.strip() or filename.strip() == ".pdf":
            filename = "document.pdf"

        with open(filename, 'wb') as f:
            f.write(pdf_data)

        logging.info(f"Successfully downloaded '{os.path.abspath(filename)}'")
        return True

    except TimeoutException:
        logging.error("Page load timed out. Please check the URL and your connection.")
        return False
    except WebDriverException as e:
        logging.error(f"A WebDriver error occurred: {e}")
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return False


def get_embed_url(url):
    """Converts a Scribd document URL to its embed equivalent."""
    if '/document/' in url:
        match = re.search(r'/(\d+)/', url)
        if match:
            document_id = match.group(1)
            return f"https://www.scribd.com/embeds/{document_id}/content"
    return url


def main():
    """Parses arguments and orchestrates the download."""
    parser = argparse.ArgumentParser(
        description='A script to download documents from Scribd as PDF files.',
        epilog='Example: python3 sdl.py "https://www.scribd.com/document/123456789/My-Document" --crop 1 3 1,5 1.5'
    )
    parser.add_argument('url', help='The URL of the Scribd document to download.')
    parser.add_argument(
        '--crop',
        nargs=4,
        type=float_with_comma,
        metavar=('TOP', 'BOTTOM', 'LEFT', 'RIGHT'),
        help='Crop the PDF by removing margins (in cm). Accepts both "." and "," as decimal separators.'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=300,
        help='Set the timeout in seconds for long-running operations (default: 300).'
    )
    args = parser.parse_args()

    if "scribd.com" not in args.url:
        logging.warning("This script is intended for scribd.com URLs. It may not work correctly with other sites.")

    embed_url = get_embed_url(args.url)

    driver = setup_driver()
    if driver:
        try:
            # Set the command executor timeout
            driver.command_executor.set_timeout(args.timeout)

            download_document_as_pdf(driver, embed_url, args.url, args.crop, args.timeout)
        finally:
            logging.info("Closing the browser.")
            driver.quit()

if __name__ == '__main__':
    main()
