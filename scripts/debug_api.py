import requests
import time
from datetime import datetime

def test_fallback():
    url = "http://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": 1, "pz": 20, "po": 1, "np": 1, 
        "ut": "bd1d9ddb04089700cf9c27f6f7426281", "fltt": 2, "invt": 2,
        "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
        "fields": "f12,f14,f3,f2",
        "_": int(time.time() * 1000)
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    print(f"Testing Fallback URL: {url}")
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        print(f"Status: {resp.status_code}")
        data = resp.json()
        if data.get('data'):
            print(f"Got {len(data['data']['diff'])} items")
            print(data['data']['diff'][0])
        else:
            print("No data")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_fallback()
