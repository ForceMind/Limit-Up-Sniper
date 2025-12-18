
import akshare as ak
import pandas as pd
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.data_provider import data_provider

def test_market_data():
    print("Testing fetch_all_market_data (Sina)...")
    try:
        df = data_provider.fetch_all_market_data()
        if df is None or df.empty:
            print("[-] fetch_all_market_data returned None or empty.")
        else:
            print(f"[+] Got {len(df)} rows.")
            print("Columns:", df.columns.tolist())
            print("Sample row:\n", df.iloc[0])
            
            # Test calculation logic
            limit_up_count = 0
            broken_count = 0
            for _, row in df.iterrows():
                try:
                    code = str(row['code'])
                    current = float(row['current'])
                    prev_close = float(row['prev_close'])
                    high = float(row.get('high', 0))
                    
                    if current == 0 or prev_close == 0: continue

                    is_20cm = code.startswith('30') or code.startswith('68')
                    limit_ratio = 1.2 if is_20cm else 1.1
                    limit_price = round(prev_close * limit_ratio, 2)
                    
                    if current >= limit_price:
                        limit_up_count += 1
                    elif high >= limit_price and current < limit_price:
                        broken_count += 1
                except:
                    continue
            print(f"Calculated Limit Up: {limit_up_count}")
            print(f"Calculated Broken: {broken_count}")

    except Exception as e:
        print(f"[-] Error: {e}")

def test_alternatives():
    print("\nTesting AKShare EastMoney Spot...")
    try:
        df = ak.stock_zh_a_spot_em()
        print(f"[+] EM Spot returned {len(df)} rows.")
        print("Columns:", df.columns.tolist())
    except Exception as e:
        print(f"[-] EM Spot failed: {e}")

if __name__ == "__main__":
    test_market_data()
    test_alternatives()
