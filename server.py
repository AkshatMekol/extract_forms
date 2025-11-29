from fastapi.middleware.cors import CORSMiddleware
import os
import asyncio
import requests
from io import BytesIO
from PyPDF2 import PdfReader, PdfWriter
from fastapi import FastAPI, HTTPException
from helpers import extract_form_pages 
from s3_utils import list_s3_pdfs, fetch_pdf
from utils.mongo_utils import vector_collection, is_document_complete

app = FastAPI()

origins = [
    "http://localhost:8080",
    "http://192.168.1.5:8080",
    "https://tenderbharat.vercel.app",
    "http://localhost:3000",
    "https://www.bidindia.site",
    "https://www.bidindia.co.in",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def process_single_tender(tender_id: str):
    print(f"\n===============================")
    print(f"▶ START tender: {tender_id}")
    print(f"===============================")

    report = {
        "tender_id": tender_id,
        "processed_docs": 0,
        "skipped_docs": 0,
        "empty_docs": 0,
        "scanned_pages": 0,
        "regular_pages": 0,
        "errors": []
    }

    s3_prefix = f"tender-documents/{tender_id}/"
    print(f"📂 Fetching S3 PDFs from prefix: {s3_prefix}")

    pdf_keys = await list_s3_pdfs(s3_prefix)
    print(f"📄 Found {len(pdf_keys)} PDFs")

    for pdf_key in pdf_keys:
        document_name = os.path.basename(pdf_key)
        print(f"📄 Document: {document_name}")

        if await asyncio.to_thread(is_document_complete, tender_id, document_name):
            print(f"⏩ Already processed, skipping")
            report["skipped_docs"] += 1
            continue

        try:
            pdf_bytes = await fetch_pdf(pdf_key)
            page_errors = 0

            extracted_pdf_bytes, num_pages = await extract_form_pages(pdf_bytes, document_name)

            # If pages extraction fails or too many errors, abort this PDF
            if num_pages == 0 and page_errors > 3:
                print(f"❌ Too many errors, aborting PDF: {document_name}")
                report["errors"].append(f"{document_name} aborted due to too many page errors")
                continue

            output_path = f"fillable_forms_{document_name}"
            if num_pages > 0:
                reader = PdfReader(extracted_pdf_bytes)
                writer = PdfWriter()
                for page in reader.pages:
                    writer.add_page(page)

                with open(output_path, "wb") as f:
                    writer.write(f)

                print(f"\n🎯 Combined FORM pages PDF saved as: {output_path}")
                report["processed_docs"] += 1
                if page_errors > 0:
                    report["errors"].append(f"{document_name} had {page_errors} page errors")

            else:
                print(f"\n⚠️ No FORM pages found in {document_name}")
                report["empty_docs"] += 1

            # Mark document complete after each PDF
            await asyncio.to_thread(mark_document_complete, tender_id, document_name)

        except Exception as e:
            print(f"❌ Error processing {document_name}: {e}")
            report["errors"].append(f"{document_name}: {str(e)}")

    print(f"\n✅ Finished tender {tender_id}")
    print(f"📊 Report: {report}")
    return report

@app.post("/process/{tender_id}")
async def route_process(tender_id: str):
    print(f"\n🌐 API CALL → /process/{tender_id}")
    try:
        return await process_single_tender(tender_id)
    except Exception as e:
        print(f"❌ API ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))
