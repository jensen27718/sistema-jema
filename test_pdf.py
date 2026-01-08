import fitz
from PIL import Image
import io
import os

def test_pdf_conversion(pdf_path):
    if not os.path.exists(pdf_path):
        print(f"File {pdf_path} not found.")
        return

    try:
        with open(pdf_path, "rb") as f:
            file_content = f.read()
        
        doc = fitz.open(stream=file_content, filetype="pdf")
        print(f"PDF opened successfully. Pages: {doc.page_count}")
        
        if doc.page_count > 0:
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            output_path = "test_preview.webp"
            img.save(output_path, format='WEBP', quality=85)
            print(f"Preview saved to {output_path}")
        
        doc.close()
    except Exception as e:
        print(f"Error during conversion: {e}")

if __name__ == "__main__":
    # Look for any PDF in the workspace to test
    print("Testing PyMuPDF import and basic functionality...")
    try:
        import fitz
        print("fitz imported successfully.")
    except ImportError:
        print("fitz NOT found.")
