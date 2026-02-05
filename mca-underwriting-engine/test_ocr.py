#!/usr/bin/env python3
"""Test OCR extraction on bank statement PDFs."""

import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core_logic.ocr_engine import extract_from_pdf, extract_text_ocr, OCR_AVAILABLE


def test_pdf(pdf_path: str):
    print(f"\n{'='*60}")
    print(f"Testing: {pdf_path}")
    print('='*60)

    result = extract_from_pdf(pdf_path)

    print(f"Success: {result['success']}")
    print(f"Method: {result.get('extraction_method', 'N/A')}")
    print(f"Bank: {result['bank_name']}")
    print(f"Account: {result['account_number']}")
    print(f"Transactions found: {len(result['transactions'])}")

    if result['fraud_flags']:
        print(f"FRAUD FLAGS: {result['fraud_flags']}")

    if result['errors']:
        print(f"Errors: {result['errors']}")

    if result.get('warnings'):
        print(f"Warnings: {result['warnings']}")

    if result['transactions']:
        print("\nFirst 5 transactions:")
        for t in result['transactions'][:5]:
            print(f"  {t['date']} | {t['description'][:40]:<40} | ${t['amount']:>10,.2f}")

        print(f"\nLast 5 transactions:")
        for t in result['transactions'][-5:]:
            print(f"  {t['date']} | {t['description'][:40]:<40} | ${t['amount']:>10,.2f}")

    return result['success']


def test_ocr_availability():
    """Verify OCR dependencies are installed."""
    print("="*60)
    print("OCR DEPENDENCY CHECK")
    print("="*60)

    print(f"pytesseract/pdf2image available: {OCR_AVAILABLE}")

    if OCR_AVAILABLE:
        import pytesseract
        try:
            version = pytesseract.get_tesseract_version()
            print(f"Tesseract version: {version}")
        except Exception as e:
            print(f"Tesseract binary check: {e}")

        import shutil
        pdftoppm = shutil.which("pdftoppm")
        print(f"pdftoppm (poppler): {pdftoppm or 'NOT FOUND'}")
    else:
        print("WARNING: pytesseract or pdf2image not installed")
        print("  Install with: pip install pytesseract pdf2image Pillow")
        print("  Also need: apt-get install tesseract-ocr poppler-utils")

    print()
    return OCR_AVAILABLE


def test_ocr_fallback_logic():
    """Test that the OCR fallback path is reachable."""
    print("="*60)
    print("OCR FALLBACK LOGIC TEST")
    print("="*60)

    # Test with non-existent file
    result = extract_from_pdf("/tmp/nonexistent.pdf")
    assert not result["success"], "Should fail for nonexistent file"
    assert result["errors"], "Should have errors"
    print("PASS: Non-existent file handled correctly")

    # Verify the extract_text_ocr function is callable
    ocr_text = extract_text_ocr("/tmp/nonexistent.pdf")
    assert ocr_text == "", "Should return empty string for nonexistent file"
    print("PASS: OCR fallback function is callable and handles errors")

    # Verify result dict has new fields
    assert "extraction_method" in result, "Missing extraction_method field"
    assert "warnings" in result, "Missing warnings field"
    print("PASS: Result dict has extraction_method and warnings fields")

    print()


if __name__ == "__main__":
    ocr_ok = test_ocr_availability()
    test_ocr_fallback_logic()

    # Test all PDFs in input_pdfs folder
    pdf_folder = Path(os.path.join(os.path.dirname(__file__), "input_pdfs"))

    if not pdf_folder.exists():
        print("No input_pdfs folder found")
        print("\nAll baseline tests passed. Add PDFs to input_pdfs/ for extraction testing.")
        sys.exit(0)

    pdfs = list(pdf_folder.glob("*.pdf"))

    if not pdfs:
        print("No PDF files found in input_pdfs/")
        print("Please add bank statement PDFs to test extraction.")
        print("\nAll baseline tests passed.")
        sys.exit(0)

    success_count = 0
    for pdf in pdfs:
        if test_pdf(str(pdf)):
            success_count += 1

    print(f"\n{'='*60}")
    print(f"RESULTS: {success_count}/{len(pdfs)} PDFs processed successfully")
    print('='*60)
