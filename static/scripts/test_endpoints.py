import urllib.request
import urllib.error
import sys

endpoints = [
    "http://127.0.0.1:5050/case-studies",
    "http://127.0.0.1:5050/case-studies/enterprise-data-governance-mdm",
    "http://127.0.0.1:5050/case-studies/automated-bing-ads-ingestion",
    "http://127.0.0.1:5050/industries/retail/case-studies",
    "http://127.0.0.1:5050/industries/bfsi/case-studies",
    "http://127.0.0.1:5050/industries/manufacturing/case-studies",
    "http://127.0.0.1:5050/industries/healthcare/case-studies"
]

print("Testing Case Study Endpoints...")
failures = 0

for ep in endpoints:
    try:
        req = urllib.request.Request(
            ep, 
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            code = response.getcode()
            print(f"[OK] {ep} - Status: {code}")
    except urllib.error.HTTPError as e:
        print(f"[FAIL] {ep} - HTTP Error: {e.code}")
        failures += 1
    except Exception as e:
        print(f"[FAIL] {ep} - Error: {e}")
        failures += 1

if failures > 0:
    print(f"\nCompleted with {failures} failures.")
    sys.exit(1)
else:
    print("\nAll endpoints verified successfully (HTTP 200).")
