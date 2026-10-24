import base64
import json
import os
import time
import glob
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("OPENROUTER_API_KEY")

cache_file = "dataset/evidence/images_ocr_cache.json"
cache = {}
if os.path.exists(cache_file):
    with open(cache_file, "r") as f:
        cache = json.load(f)

img_files = sorted(glob.glob("dataset/evidence/images/*.png"))

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

prompt = (
    "Extract all information from this system screenshot in detail. "
    "Include all user_ids (e.g. user_XX), resource_ids (e.g. account_XX, search_XX, support_XX, analytics_XX, backup_XX, data_flow_XX, audit_record_XX, tombstone_XX), "
    "emails, names, phone numbers, timestamps, statuses, tables, and column values. "
    "Output clearly as plain text."
)

models = [
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3.5-super-vl:free",
    "openrouter/free"
]

for p in img_files:
    fname = os.path.basename(p)
    if fname in cache:
        print(f"[CACHED] {fname}")
        continue
    
    print(f"[PROCESSING] {fname}...")
    with open(p, "rb") as f:
        b64_img = base64.b64encode(f.read()).decode("utf-8")
        
    success = False
    for m in models:
        payload = {
            "model": m,
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
        try:
            print(f"  Trying model: {m}...")
            res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=60)
            if res.status_code == 200:
                data = res.json()
                content = data["choices"][0]["message"]["content"]
                if content and len(content.strip()) > 30:
                    cache[fname] = content
                    print(f"  Success ({m}): {len(content)} chars")
                    with open(cache_file, "w") as f:
                        json.dump(cache, f, indent=2)
                    success = True
                    break
            else:
                print(f"  Failed with {m}: {res.status_code}")
        except Exception as e:
            print(f"  Error with {m}: {e}")
        time.sleep(2)
        
    time.sleep(2)

print(f"Finished! Cached {len(cache)}/{len(img_files)} images.")
