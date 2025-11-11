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
from selenium_stealth import stealth

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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

def download_document_as_pdf(driver, url):
    """Navigates to the URL and saves the document as a PDF."""
    try:
        logging.info(f"Navigating to: {url}")
        driver.get(url)

        WebDriverWait(driver, 120).until(
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

        # Sanitize title for filename
        title = driver.title
        filename = sanitize_filename(title) + ".pdf"

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
