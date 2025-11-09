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
import shutil
from PIL import Image

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

def scroll_to_bottom(driver):
    """Scrolls to the bottom of the page to ensure all content is loaded."""
    logging.info("Scrolling to load all pages of the document...")
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
    logging.info("Finished scrolling.")

def create_pdf_from_images(image_folder, pdf_filename):
    """Converts a list of images into a single PDF file."""
    images = []
    for filename in sorted(os.listdir(image_folder)):
        if filename.endswith(".png"):
            filepath = os.path.join(image_folder, filename)
            im = Image.open(filepath)
            im = im.convert("RGB")
            images.append(im)

    if images:
        images[0].save(pdf_filename, save_all=True, append_images=images[1:])
        logging.info(f"Successfully created PDF: {pdf_filename}")
    else:
        logging.warning("No images found to create a PDF.")

def download_document_as_pdf(driver, url):
    """Navigates to the URL and saves the document as a PDF."""
    image_folder = ""
    try:
        logging.info(f"Navigating to: {url}")
        driver.get(url)

        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".document_scroller"))
        )
        logging.info("Document page loaded successfully.")

        scroll_to_bottom(driver)

        # Create a directory to store the screenshots
        title = sanitize_filename(driver.title)
        image_folder = title
        if not os.path.exists(image_folder):
            os.makedirs(image_folder)

        # Take a screenshot of each page
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[id^="page"]'))
        )
        pages = driver.find_elements(By.CSS_SELECTOR, 'div[id^="page"]')
        logging.info(f"Found {len(pages)} pages.")
        for i, page in enumerate(pages):
            driver.execute_script("arguments[0].scrollIntoView();", page)
            time.sleep(1)
            page.screenshot(os.path.join(image_folder, f'page_{i+1}.png'))
            logging.info(f"Screenshot taken for page {i+1}")

        logging.info(f"All pages have been screenshotted and saved in the '{image_folder}' directory.")

        # Convert images to PDF
        pdf_filename = title + ".pdf"
        create_pdf_from_images(image_folder, pdf_filename)

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
    finally:
        # Clean up the screenshot directory
        if image_folder and os.path.exists(image_folder):
            shutil.rmtree(image_folder)
            logging.info(f"Cleaned up screenshot directory: {image_folder}")


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

    driver = setup_driver()
    if driver:
        try:
            download_document_as_pdf(driver, args.url)
        finally:
            logging.info("Closing the browser.")
            driver.quit()

if __name__ == '__main__':
    main()
