import fitz

def create_dummy_pdf(output_path, num_pages=20):
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page()
        page.insert_text((50, 72), f"Page {i + 1}")
    doc.save(output_path)
    doc.close()

if __name__ == "__main__":
    create_dummy_pdf("dummy.pdf")
