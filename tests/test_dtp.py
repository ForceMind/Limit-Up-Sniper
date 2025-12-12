import requests
import time

def check_dtp():
    date_str = time.strftime('%Y%m%d')
    base_url = "https://push2ex.eastmoney.com/getTopicDtpPool"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    params = {
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "dpt": "wz.ztzt",
        "Pageindex": 0,
        "pagesize": 20,
        "sort": "fbt:asc",
        "date": date_str,
        "_": int(time.time() * 1000)
    }
    
    try:
        resp = requests.get(base_url, params=params, headers=headers, timeout=5)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            if data.get('data'):
                pool = data['data'].get('pool', [])
                print(f"Limit Down Count: {len(pool)}")
                if pool:
                    print(f"Sample: {pool[0]}")
            else:
                print("No data found or API might be wrong.")
                print(data)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_dtp()
