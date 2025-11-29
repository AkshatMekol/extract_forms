# CLASSIFY_PROMPT_TEMPLATE = """
#                             You are a strict classifier for tender documents.
                            
#                             Your task is to identify ONLY the pages that must be filled out by the contractor and sent back to the client.
#                             These pages contain blanks, empty fields, places to write, tables to fill, or areas for signatures/seals.
                            
#                             Ignore any page that is purely:
#                             - Instructions, clauses, or general text
#                             - Tender descriptions
#                             - Annexures with information already filled
#                             - Tables that only display data without requiring input
                            
#                             Respond with ONE WORD ONLY: FORM or OTHER.
                            
#                             Page content:
#                             {content}
#                             """

# def is_scanned_page(page):
#     text = page.get_text() or ""
#     return len(text.strip()) < 10

# def render_page_to_image(page) -> bytes:
#     image = page.get_pixmap(dpi=200).pil_image.convert("RGB")
#     resized = image.resize((image.width // 2, image.height // 2))
#     buffer = io.BytesIO()
#     resized.save(buffer, format="JPEG", quality=40)
#     return buffer.getvalue()

# def groq_classify_page(page) -> str:
#     prompt = CLASSIFY_PROMPT_TEMPLATE.format(content="Image attached")
#     img_bytes = render_page_to_image(page)
#     ans = query_groq(img_bytes, prompt).strip().upper()
#     return "FORM" if "FORM" in ans else "OTHER"
  
# def deepseek_classify_page(page_text: str):
#     prompt = CLASSIFY_PROMPT_TEMPLATE.format(content=page_text)
#     ans = query_deepseek(prompt).strip().upper()
#     return "FORM" if "FORM" in ans else "OTHER"

# def extract_form_pages(pdf_bytes: BytesIO, pdf_name: str):
#     reader = PdfReader(pdf_bytes)
#     doc = fitz.open(stream=pdf_bytes, filetype="pdf")
#     form_pages = []

#     for i, page in enumerate(doc):
#         page_text = page.get_text()
#         scanned = is_scanned_page(page)

#         if scanned:
#             classification = groq_classify_page(page)
#         else:
#             classification = deepseek_classify_page(page_text)

#         print(f"📄 Processing {pdf_name} - Page {i+1}/{len(doc)} | Scanned={scanned} | Result={classification}")

#         if classification == "FORM":
#             form_pages.append(i)

#     writer = PdfWriter()
#     for p in form_pages:
#         writer.add_page(reader.pages[p])

#     output_pdf_bytes = BytesIO()
#     if form_pages:
#         writer.write(output_pdf_bytes)
#     output_pdf_bytes.seek(0)
#     return output_pdf_bytes, len(form_pages)



import io
import fitz
import asyncio
from PyPDF2 import PdfReader, PdfWriter
from .config import MAX_PROCESSES_GROQ, MAX_PROCESSES_DEEPSEEK, CLASSIFY_PROMPT
from .llm_utils import query_groq, query_deepseek

MAX_PROCESSES_GROQ = 4
MAX_PROCESSES_DEEPSEEK = 8

CLASSIFY_PROMPT = """
                  You are a strict classifier for tender documents.
                  
                  Your task is to identify ONLY the pages that must be filled out by the contractor and sent back to the client.
                  These pages contain blanks, empty fields, places to write, tables to fill, or areas for signatures/seals.
                  
                  Ignore any page that is purely:
                  - Instructions, clauses, or general text
                  - Tender descriptions
                  - Annexures with information already filled
                  - Tables that only display data without requiring input
                  
                  Respond with ONE WORD ONLY: FORM or OTHER.
                  
                  Page content:
                  {content}
                  """

def is_scanned_page(page):
    text = page.get_text() or ""
    return len(text.strip()) < 10

def render_page_to_image(page) -> bytes:
    image = page.get_pixmap(dpi=200).pil_image.convert("RGB")
    resized = image.resize((image.width // 2, image.height // 2))
    buffer = io.BytesIO()
    resized.save(buffer, format="JPEG", quality=40)
    return buffer.getvalue()

def groq_classify_page(page) -> str:
    prompt = CLASSIFY_PROMPT_TEMPLATE.format(content="Image attached")
    img_bytes = render_page_to_image(page)
    ans = query_groq(img_bytes, prompt).strip().upper()
    return "FORM" if "FORM" in ans else "OTHER"

async def groq_worker(page, semaphore, page_num, pdf_name):
    async with semaphore:
        print(f"🚀 Dispatched to GROQ: {pdf_name} - Page {page_num} (scanned)")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, groq_classify_page, page)

def deepseek_classify_page(page_text: str):
    prompt = CLASSIFY_PROMPT_TEMPLATE.format(content=page_text)
    ans = query_deepseek(prompt).strip().upper()
    return "FORM" if "FORM" in ans else "OTHER"

async def deepseek_worker(page_text, semaphore, page_num, pdf_name):
    async with semaphore:
        print(f"🚀 Dispatched to DeepSeek: {pdf_name} - Page {page_num} (regular)")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, deepseek_classify_page, page_text)
      
async def extract_form_pages(pdf_bytes: BytesIO, pdf_name: str):
    reader = PdfReader(pdf_bytes)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    form_pages = []

    groq_semaphore = asyncio.Semaphore(MAX_PROCESSES_GROQ)
    deepseek_semaphore = asyncio.Semaphore(MAX_PROCESSES_DEEPSEEK)

    tasks = []
    page_indices = []

    for i, page in enumerate(doc):
        page_text = page.get_text()
        scanned = is_scanned_page(page)
        page_indices.append(i)

        if scanned:
            report["scanned_pages"] += 1
            tasks.append(groq_worker(page, groq_semaphore, i+1, pdf_name))
        else:
            report["regular_pages"] += 1
            tasks.append(deepseek_worker(page_text, deepseek_semaphore, i+1, pdf_name))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    page_errors = 0
    for i, classification in zip(page_indices, results):
        if isinstance(classification, Exception):
            print(f"❌ Error on {pdf_name} - Page {i+1}: {classification}")
            page_errors += 1
            continue

        print(f"📄 Processing {pdf_name} - Page {i+1}/{len(doc)} | Result={classification}")
        if classification == "FORM":
            form_pages.append(i+1)

    writer = PdfWriter()
    for p in form_pages:
        writer.add_page(reader.pages[p])

    output_pdf_bytes = BytesIO()
    if form_pages:
        writer.write(output_pdf_bytes)
    output_pdf_bytes.seek(0)

    return output_pdf_bytes, len(form_pages), page_errors
