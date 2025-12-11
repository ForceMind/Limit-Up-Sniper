import requests
import time

def debug_fields():
    # Get a list of stocks, hopefully one is limit up
    url = "http://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": 1, "pz": 20, "po": 1, "np": 1, 
        "ut": "bd1d9ddb04089700cf9c27f6f7426281", "fltt": 2, "invt": 2,
        "fid": "f3", # Sort by change percent desc
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
        "fields": ",".join([f"f{i}" for i in range(1, 200)]),
        "_": int(time.time() * 1000)
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        data = resp.json()
        if data.get('data'):
            print("Top stock:")
            print(data['data']['diff'][0])
    except Exception as e:
        print(e)

if __name__ == "__main__":
    debug_fields()