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

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_driver():
    """Sets up the headless Chrome WebDriver."""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_experimental_option('prefs', {
        'printing.print_to_pdf': True,
    })
    service = ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

def sanitize_filename(filename):
    """Sanitizes a string to be used as a valid filename."""
    sanitized = re.sub(r'[\\/*?:"<>|]', "", filename)
    return sanitized.replace(' ', '_')

def download_document_as_pdf(driver, url):
    """Navigates to the URL and saves the document as a PDF."""
    try:
        logging.info(f"Navigating to: {url}")
        driver.get(url)

        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".document_scroller"))
        )
        logging.info("Document page loaded successfully.")

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

        # Print page to PDF
        logging.info("Printing page to PDF...")
        title = sanitize_filename(driver.title)
        pdf_filename = title + ".pdf"

        # Use Chrome's print to PDF feature
        result = driver.execute_cdp_cmd(
            "Page.printToPDF", {
                "landscape": False,
                "printBackground": True,
                "preferCSSPageSize": True,
            }
        )

        with open(pdf_filename, "wb") as f:
            f.write(base64.b64decode(result['data']))

        logging.info(f"Successfully created PDF: {pdf_filename}")

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
        epilog='Example: python3 sdl.py "https://www.scribd.com/document/123456789/My-Document"'
    )
    parser.add_argument('url', help='The URL of the Scribd document to download.')
    args = parser.parse_args()

    if "scribd.com" not in args.url:
        logging.warning("This script is intended for scribd.com URLs. It may not work correctly with other sites.")

    embed_url = get_embed_url(args.url)

    driver = setup_driver()
    if driver:
        try:
            download_document_as_pdf(driver, embed_url)
        finally:
            logging.info("Closing the browser.")
            driver.quit()

if __name__ == '__main__':
    main()
