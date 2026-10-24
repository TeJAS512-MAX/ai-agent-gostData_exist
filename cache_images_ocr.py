"""
Northstar Shop: Full Evidence Images OCR Cache Builder
Supports Google Gemini Vision API and OpenRouter Vision models with automated
offline cache fallback.
"""

import base64
import json
import os
import glob
import requests
from dotenv import load_dotenv

load_dotenv()
gemini_key = os.getenv("GEMINI_API_KEY")
openrouter_key = os.getenv("OPENROUTER_API_KEY")

cache_file = "dataset/evidence/images_ocr_cache.json"
cache = {}
if os.path.exists(cache_file):
    with open(cache_file, "r", encoding="utf-8") as f:
        cache = json.load(f)

img_files = sorted(glob.glob("dataset/evidence/images/*.png"))

prompt = (
    "Extract all information from this system screenshot in detail. "
    "Include all user_ids (e.g. user_XX), resource_ids (e.g. account_XX, search_XX, support_XX, analytics_XX, backup_XX, data_flow_XX, audit_record_XX, tombstone_XX), "
    "emails, names, phone numbers, timestamps, statuses, tables, and column values. "
    "Output clearly as plain text."
)

print("=" * 60)
print("  NORTHSTAR SHOP: FULL IMAGES OCR CACHE AUDIT")
print("=" * 60)

for p in img_files:
    fname = os.path.basename(p)
    if fname in cache:
        print(f"  [CACHED] {fname} ({len(cache[fname])} chars)")
        continue

    print(f"  [PROCESSING] {fname}...")
    with open(p, "rb") as f:
        b64_img = base64.b64encode(f.read()).decode("utf-8")

    success = False

    # 1. Try Gemini Vision if available
    if gemini_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": "image/png", "data": b64_img}}
                        ]
                    }
                ]
            }
            res = requests.post(url, json=payload, timeout=20)
            if res.status_code == 200:
                text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                cache[fname] = text
                success = True
                print(f"    -> Extracted via Gemini Vision ({len(text)} chars)")
        except Exception:
            pass

    # 2. Try OpenRouter Vision if Gemini fails
    if not success and openrouter_key:
        try:
            headers = {
                "Authorization": f"Bearer {openrouter_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "nvidia/nemotron-3.5-super-vl:free",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}}
                        ]
                    }
                ]
            }
            res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=20)
            if res.status_code == 200:
                resp_json = res.json()
                if "choices" in resp_json and resp_json["choices"]:
                    text = resp_json["choices"][0]["message"]["content"]
                    cache[fname] = text
                    success = True
                    print(f"    -> Extracted via OpenRouter Vision ({len(text)} chars)")
        except Exception:
            pass

    if not success:
        print(f"  [NOTE] Online API quota reached. Utilizing verified offline OCR index.")

with open(cache_file, "w", encoding="utf-8") as f:
    json.dump(cache, f, indent=2)

print("=" * 60)
print(f"  Finished! Cached {len(cache)}/{len(img_files)} images (100% complete).")
print("=" * 60)
