import io
import fitz
import asyncio
from PIL import Image
from PyPDF2 import PdfReader, PdfWriter
from utils.llm_utils import query_groq, query_deepseek
from config import MAX_PROCESSES_GROQ, MAX_PROCESSES_DEEPSEEK, CLASSIFY_PROMPT

def is_scanned_page(page):
    text = page.get_text() or ""
    return len(text.strip()) < 10

def render_page_to_image(page) -> bytes:
    pix = page.get_pixmap(dpi=200)
    mode = "RGB" if pix.alpha == 0 else "RGBA"
    img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
    resized = img.resize((img.width // 2, img.height // 2))
    buffer = io.BytesIO()
    resized.save(buffer, format="JPEG", quality=40)
    return buffer.getvalue()

def groq_classify_page(page) -> str:
    prompt = CLASSIFY_PROMPT.format(content="Image attached")
    img_bytes = render_page_to_image(page)
    ans = query_groq(img_bytes, prompt).strip().upper()
    return "FORM" if "FORM" in ans else "OTHER"

async def groq_worker(page, semaphore, page_num, pdf_name):
    async with semaphore:
        print(f"🚀 Dispatched to GROQ: {pdf_name} - Page {page_num} (scanned)")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, groq_classify_page, page)

def deepseek_classify_page(page_text: str):
    prompt = CLASSIFY_PROMPT.format(content=page_text)
    ans = query_deepseek(prompt).strip().upper()
    return "FORM" if "FORM" in ans else "OTHER"

async def deepseek_worker(page_text, semaphore, page_num, pdf_name):
    async with semaphore:
        print(f"🚀 Dispatched to DeepSeek: {pdf_name} - Page {page_num} (regular)")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, deepseek_classify_page, page_text)
      
async def extract_form_pages(pdf_bytes: io.BytesIO, pdf_name: str):
    reader = PdfReader(pdf_bytes)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    form_pages = []

    groq_semaphore = asyncio.Semaphore(MAX_PROCESSES_GROQ)
    deepseek_semaphore = asyncio.Semaphore(MAX_PROCESSES_DEEPSEEK)

    tasks = []
    page_indices = []
    scanned_count = 0
    regular_count = 0

    for i, page in enumerate(doc):
        page_text = page.get_text()
        scanned = is_scanned_page(page)
        page_indices.append(i)

        if scanned:
            scanned_count += 1
            tasks.append(groq_worker(page, groq_semaphore, i+1, pdf_name))
        else:
            regular_count += 1
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
            form_pages.append(i+1)  # 1-based

    return form_pages, scanned_count, regular_count, page_errors
