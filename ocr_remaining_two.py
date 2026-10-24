import base64
import json
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("OPENROUTER_API_KEY")

cache_file = "dataset/evidence/images_ocr_cache.json"
with open(cache_file, "r") as f:
    cache = json.load(f)

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

remaining = [
    "dataset/evidence/images/deleted_account_reference_20260310.png",
    "dataset/evidence/images/marketing_profile_console.png"
]

for p in remaining:
    fname = os.path.basename(p)
    if fname in cache:
        print(f"Already cached: {fname}")
        continue
    
    print(f"Processing: {fname}...")
    with open(p, "rb") as f:
        b64_img = base64.b64encode(f.read()).decode("utf-8")
        
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
    
    for attempt in range(5):
        try:
            print(f"  Attempt {attempt+1}...")
            res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=60)
            if res.status_code == 200:
                resp_json = res.json()
                if "choices" in resp_json and resp_json["choices"]:
                    content = resp_json["choices"][0]["message"]["content"]
                    cache[fname] = content
                    with open(cache_file, "w") as f:
                        json.dump(cache, f, indent=2)
                    print(f"  Success: {len(content)} chars")
                    break
            else:
                print(f"  HTTP {res.status_code}: {res.text[:150]}")
        except Exception as e:
            print(f"  Exception: {e}")
        time.sleep(4)

print("Done! Total cached:", len(cache))
