import re
import time
import base64
import requests
from groq import Groq
from io import BytesIO
from utils.config import GROQ_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_API_KEY

groq_client = Groq(api_key=GROQ_API_KEY)

def query_groq(pil_image_bytes: bytes, prompt: str) -> str:
    img_base64 = base64.b64encode(pil_image_bytes).decode("utf-8")
    image_data_url = f"data:image/jpeg;base64,{img_base64}"

    response = groq_client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_data_url}}
            ]
        }],
        temperature=0.3,
        max_completion_tokens=4096
    )
    return response.choices[0].message.content.strip()

def clean_llm_output(text: str) -> str:
    text = re.sub(r"```(?:markdown)?\s*", "", text)
    text = re.sub(r"\s*```", "", text)
    text = re.sub(r"\$\$(.*?)\$\$", "", text, flags=re.DOTALL)
    text = re.sub(r"\$(.*?)\$", "", text, flags=re.DOTALL)
    return text.strip()

def query_deepseek(prompt, retries=3, delay=2):
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a tender consultant."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0
    }

    for attempt in range(1, retries + 1):
        try:
            response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
            data = response.json()

            if "choices" in data:
                cleaned = clean_llm_output(data["choices"][0]["message"]["content"])
                return cleaned

            elif "error" in data:
                raise RuntimeError(data["error"]["message"])

            else:
                raise RuntimeError(f"Unexpected response: {data}")

        except Exception as e:
            print(f"DeepSeek error: {e}")
            if attempt < retries:
                time.sleep(delay * attempt)
            else:
                raise
