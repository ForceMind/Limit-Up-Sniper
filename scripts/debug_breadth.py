import requests
import time
import akshare as ak

def test_market_breadth_ak():
    print("Fetching data via AKShare...")
    try:
        df = ak.stock_zh_a_spot_em()
        print(f"Fetched {len(df)} stocks")
        
        # Columns: 序号, 代码, 名称, 最新价, 涨跌幅, ...
        # 涨跌幅 column name is usually "涨跌幅"
        
        up = len(df[df['涨跌幅'] > 0])
        down = len(df[df['涨跌幅'] < 0])
        flat = len(df[df['涨跌幅'] == 0])
        limit_down = len(df[df['涨跌幅'] < -9.5])
        
        print(f"Up: {up}, Down: {down}, Flat: {flat}, Limit Down: {limit_down}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_market_breadth_ak()