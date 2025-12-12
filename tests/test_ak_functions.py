import akshare as ak
import pandas as pd
from datetime import datetime

def test_akshare():
    print("Testing AKShare functions...")
    
    # 1. Realtime quotes (for intraday scan and market overview)
    try:
        print("Fetching stock_zh_a_spot_em...")
        df_spot = ak.stock_zh_a_spot_em()
        print(f"Spot data shape: {df_spot.shape}")
        print(df_spot.head(2))
        # Columns usually: 序号, 代码, 名称, 最新价, 涨跌幅, 涨跌额, 成交量, 成交额, 振幅, 最高, 最低, 今开, 昨收, 量比, 换手率, 市盈率-动态, 市净率
    except Exception as e:
        print(f"stock_zh_a_spot_em failed: {e}")

    # 2. Limit Up Pool
    try:
        date_str = datetime.now().strftime("%Y%m%d")
        print(f"Fetching stock_zt_pool_em for {date_str}...")
        df_zt = ak.stock_zt_pool_em(date=date_str)
        if df_zt is not None:
            print(f"ZT Pool shape: {df_zt.shape}")
            print(df_zt.head(2))
        else:
            print("ZT Pool is empty or None")
    except Exception as e:
        print(f"stock_zt_pool_em failed: {e}")

    # 3. Broken Limit Up Pool
    try:
        date_str = datetime.now().strftime("%Y%m%d")
        print(f"Fetching stock_zt_pool_zbgc_em for {date_str}...")
        df_zb = ak.stock_zt_pool_zbgc_em(date=date_str)
        if df_zb is not None:
            print(f"ZB Pool shape: {df_zb.shape}")
            print(df_zb.head(2))
        else:
            print("ZB Pool is empty or None")
    except Exception as e:
        print(f"stock_zt_pool_zbgc_em failed: {e}")

    # 4. Indices
    try:
        print("Fetching stock_zh_index_spot...")
        df_index = ak.stock_zh_index_spot()
        print(f"Index data shape: {df_index.shape}")
        print(df_index[df_index['名称'].isin(['上证指数', '深证成指', '创业板指'])])
    except Exception as e:
        print(f"stock_zh_index_spot failed: {e}")

if __name__ == "__main__":
    test_akshare()
