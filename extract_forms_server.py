from fastapi.middleware.cors import CORSMiddleware
import os
import asyncio
import requests
from io import BytesIO
from PyPDF2 import PdfReader, PdfWriter
from fastapi import FastAPI, HTTPException
from utils.s3_utils import list_s3_pdfs, fetch_pdf
from extract_forms.pdf_processing import extract_form_pages 
from utils.mongo_utils import is_form_complete, mark_form_complete

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
        "scanned_pages": 0,
        "regular_pages": 0,
        "total_page_errors": 0,  
        "errors": [],
        "form_pages": {}  
    }

    s3_prefix = f"tender-documents/{tender_id}/"
    print(f"📂 Fetching S3 PDFs from prefix: {s3_prefix}")

    pdf_keys = await list_s3_pdfs(s3_prefix)
    print(f"📄 Found {len(pdf_keys)} PDFs")

    for pdf_key in pdf_keys:
        document_name = os.path.basename(pdf_key)
        print(f"📄 Document: {document_name}")

        if await asyncio.to_thread(is_form_complete, tender_id, document_name):
            print(f"⏩ Already processed, skipping")
            report["skipped_docs"] += 1
            continue

        try:
            pdf_bytes = await fetch_pdf(pdf_key)
            form_pages, scanned_count, regular_count, page_errors = await extract_form_pages(pdf_bytes, document_name)
            report["form_pages"][document_name] = form_pages
            report["scanned_pages"] += scanned_count
            report["regular_pages"] += regular_count
            report["total_page_errors"] += page_errors

            if page_errors > 3:
                print(f"❌ Too many errors ({page_errors}), aborting PDF: {document_name}")
                report["errors"].append(f"{document_name} aborted due to {page_errors} page errors")
                continue

            await asyncio.to_thread(mark_form_complete, tender_id, document_name, form_pages)
            report["processed_docs"] += 1

            if page_errors > 0:
                report["errors"].append(f"{document_name} had {page_errors} page errors")

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
