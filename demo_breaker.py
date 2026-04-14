import requests
import time

URL = "http://localhost:8000/v1/chat/completions"
HEADERS = {
    "Authorization": "Bearer test-key",
    "Content-Type": "application/json",
}

payload = {
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "hello"}],
}

def call():
    try:
        r = requests.post(URL, json=payload, headers=HEADERS, timeout=5)
        print(f"{r.status_code} → {r.json().get('circuit', {})}")
    except Exception as e:
        print("request failed:", str(e))


print("\n--- Trigger failures ---")
for i in range(6):
    call()
    time.sleep(0.5)

print("\n--- Circuit should be OPEN (503 expected) ---")
call()

print("\n--- Waiting for cooldown ---")
time.sleep(31)

print("\n--- Half-open probe ---")
call()

print("\n--- Recovery ---")
call()