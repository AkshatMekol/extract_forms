import zipfile
from io import BytesIO
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from s3_utils import list_s3_pdfs, fetch_pdf

app = FastAPI()

def build_zip_stream_for_tender(tender_id: str):
    prefix = f"tender-documents/{tender_id}/"
    pdf_keys = list_s3_pdfs(prefix)  # SYNC

    if not pdf_keys:
        raise HTTPException(status_code=404, detail="No PDFs found for this tender")

    zip_buffer = BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for key in pdf_keys:
            file_bytes = fetch_pdf(key)  # SYNC
            relative_path = key[len(prefix):] if key.startswith(prefix) else key
            zipf.writestr(relative_path, file_bytes)

    zip_buffer.seek(0)
    return zip_buffer


@app.get("/download_documents/{tender_id}")
def download_documents(tender_id: str):
    zip_stream = build_zip_stream_for_tender(tender_id)
    filename = f"tender_{tender_id}.zip"

    return StreamingResponse(
        zip_stream,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
