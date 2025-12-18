import akshare as ak
import pandas as pd
import requests

def check_data():
    print("Fetching spot data (Sina fallback)...")
    try:
        # Try Sina since EM is failing
        df = ak.stock_zh_a_spot()
        print("Columns:", df.columns)
        
        df = df.sort_values(by='涨跌幅', ascending=False)
        print("\nTop 5 gainers:")
        for i, row in df.head(5).iterrows():
            name = row['名称']
            code = row['代码']
            price = row['最新价']
            change = row['涨跌幅']
            prev = row['昨收']
            
            is_20cm = code.startswith('sz30') or code.startswith('sh68')
            limit_ratio = 1.2 if is_20cm else 1.1
            limit_price = round(prev * limit_ratio, 2)
            is_sealed = price >= limit_price - 0.01
            
            print(f"{name} ({code}): Price={price}, Prev={prev}, Limit={limit_price}, Change={change}%, Sealed={is_sealed}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_data()
