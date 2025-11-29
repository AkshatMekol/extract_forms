import io
from PyPDF2 import PdfReader, PdfWriter
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from s3_utils import fetch_pdf  

app = FastAPI()

def export_form_pages_pdf(tender_id: str, form_data: dict):
    writer = PdfWriter()

    for document_name, pages in form_data.items():
        if not pages:
            continue

        s3_key = f"tender-documents/{tender_id}/{document_name}"

        try:
            pdf_bytes = fetch_pdf(s3_key)   # SYNC fetch
        except Exception:
            raise HTTPException(404, f"File not found: {document_name}")

        reader = PdfReader(pdf_bytes)

        for page_num in pages:
            index = page_num - 1
            if index < 0 or index >= len(reader.pages):
                print(f"⚠️ Invalid page {page_num} in {document_name}")
                continue

            writer.add_page(reader.pages[index])

    output_buffer = io.BytesIO()
    writer.write(output_buffer)
    output_buffer.seek(0)
    return output_buffer


@app.post("/export_forms/{tender_id}")
def export_forms(tender_id: str, form_pages: dict):
    output_stream = export_form_pages_pdf(tender_id, form_pages)
    filename = f"tender_{tender_id}_forms.pdf"

    return StreamingResponse(
        output_stream,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
