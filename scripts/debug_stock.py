import requests

def check_stock_detail():
    # 驰诚股份 920407 (BSE) -> 0.920407? Or 1.920407?
    # Let's try a main board stock.
    # Find a limit up stock first.
    # From previous run: 920407 is BSE.
    # Let's try to find a SH/SZ stock.
    
    url_list = "http://push2.eastmoney.com/api/qt/clist/get"
    params_list = {
        "pn": 1, "pz": 20, "po": 1, "np": 1, 
        "ut": "bd1d9ddb04089700cf9c27f6f7426281", "fltt": 2, "invt": 2,
        "fid": "f3", 
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", # Exclude BSE for now to be safe
        "fields": "f12,f14,f3",
        "_": 123
    }
    resp = requests.get(url_list, params=params_list)
    data = resp.json()
    stock = data['data']['diff'][0]
    code = stock['f12']
    name = stock['f14']
    print(f"Checking {name} ({code})")
    
    # Construct secid
    # 0: sz, 1: sh
    secid = f"1.{code}" if code.startswith('6') else f"0.{code}"
    
    url_detail = "http://push2.eastmoney.com/api/qt/stock/get"
    params_detail = {
        "secid": secid,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fields": "f57,f58,f59,f152,f260,f261,f262,f263,f264,f265,f266,f267,f268", # Try random high fields
        "invt": 2,
        "_": 123
    }
    
    resp_detail = requests.get(url_detail, params=params_detail)
    print(resp_detail.json())

if __name__ == "__main__":
    check_stock_detail()