import akshare as ak
import requests
import pandas as pd
import time
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

class DataProvider:
    def __init__(self, logger=None):
        self.logger = logger

    def log(self, msg):
        if self.logger:
            self.logger(msg)
        else:
            print(msg)

    def _is_bse(self, code):
        return code.startswith('8') or code.startswith('4') or code.startswith('92') or code.startswith('bj')

    def _format_code(self, code):
        """Ensure code has prefix (sh/sz/bj)"""
        code = str(code)
        if code.startswith('sh') or code.startswith('sz') or code.startswith('bj'):
            return code
        
        if code.startswith('6'):
            return f"sh{code}"
        elif code.startswith('0') or code.startswith('3'):
            return f"sz{code}"
        elif code.startswith('8') or code.startswith('4') or code.startswith('9'):
            return f"bj{code}"
        return code

    def _strip_code(self, code):
        """Remove prefix"""
        return code.replace('sh', '').replace('sz', '').replace('bj', '')

    def fetch_quotes(self, codes):
        """
        Fetch real-time quotes for a list of codes.
        Returns a list of dicts with standardized fields.
        """
        if not codes:
            return []

        # Use Sina directly as requested by user (EastMoney is unstable/forbidden for quotes)
        try:
            return self._fetch_quotes_sina(codes)
        except Exception as e:
            self.log(f"[!] Sina quotes failed: {e}")
            
        return []

    def _fetch_quotes_sina(self, codes):
        # Sina supports batch, but URL length limit exists.
        # Split into batches of 50
        stocks = []
        batch_size = 50
        
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i+batch_size]
            url = "http://hq.sinajs.cn/list=" + ",".join(batch)
            headers = {"Referer": "http://finance.sina.com.cn"}
            try:
                # Use session with trust_env=False to bypass system proxy
                with requests.Session() as session:
                    session.trust_env = False
                    resp = session.get(url, headers=headers, timeout=5)
                
                resp.encoding = 'gbk'
                
                for line in resp.text.split('\n'):
                    if not line: continue
                    parts = line.split('=')
                    if len(parts) < 2: continue
                    
                    code = parts[0].split('_')[-1]
                    data_str = parts[1].strip('";')
                    if not data_str: continue
                    
                    data = data_str.split(',')
                    if len(data) < 30: continue
                    
                    name = data[0]
                    current = float(data[3])
                    prev_close = float(data[2])
                    if current == 0: current = prev_close
                    
                    change_percent = 0.0
                    if prev_close > 0:
                        change_percent = ((current - prev_close) / prev_close) * 100
                        
                    is_20cm = code.startswith('sz30') or code.startswith('sh68')
                    limit_ratio = 1.2 if is_20cm else 1.1
                    limit_up_price = round(prev_close * limit_ratio, 2)
                    
                    # Parse Sell 1 (Ask 1) for sealed check
                    # Index 20: Sell 1 Volume, Index 21: Sell 1 Price
                    ask1_vol = float(data[20])
                    ask1_price = float(data[21])
                    bid1_price = float(data[11]) # Index 11: Buy 1 Price
                    
                    # Strict Sealed Check:
                    # 1. Current price >= Limit Up Price (approx)
                    # 2. Ask 1 Volume is 0 (No sellers) OR Ask 1 Price is 0
                    # Actually, for limit up, usually Ask 1 is empty (0 volume, 0 price)
                    # OR Bid 1 Price == Limit Up Price
                    
                    is_sealed = False
                    if current >= limit_up_price - 0.01:
                        if ask1_vol == 0:
                            is_sealed = True
                    
                    stocks.append({
                        "code": code,
                        "name": name,
                        "current": current,
                        "change_percent": round(change_percent, 2),
                        "high": float(data[4]),
                        "open": float(data[1]),
                        "prev_close": prev_close,
                        "turnover": 0.0, 
                        "limit_up_price": limit_up_price,
                        "is_limit_up": is_sealed, # Use strict check
                        "ask1_vol": ask1_vol,
                        "bid1_price": bid1_price
                    })
            except Exception as e:
                self.log(f"[!] Batch fetch failed: {e}")
                continue
                
        return stocks

    def fetch_all_market_data(self):
        """
        Fetch ALL stocks for market overview and scanning.
        Returns DataFrame.
        """
        # Helper to temporarily unset proxy
        import os
        old_http = os.environ.get("HTTP_PROXY")
        old_https = os.environ.get("HTTPS_PROXY")
        os.environ.pop("HTTP_PROXY", None)
        os.environ.pop("HTTPS_PROXY", None)

        try:
            # 1. Try AKShare (EastMoney)
            try:
                self.log("[*] Fetching all market data (AKShare/EM)...")
                df = ak.stock_zh_a_spot_em()
                rename_map = {
                    '代码': 'code', '名称': 'name', '最新价': 'current', '涨跌幅': 'change_percent',
                    '涨速': 'speed', '换手率': 'turnover', '流通市值': 'circ_mv', '昨收': 'prev_close',
                    '最高': 'high', '最低': 'low', '今开': 'open', '成交额': 'amount'
                }
                df = df.rename(columns=rename_map)
                # Ensure numeric
                for col in ['current', 'change_percent', 'speed', 'turnover', 'circ_mv', 'prev_close', 'high']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                return df
            except Exception as e:
                self.log(f"[!] AKShare/EM failed: {e}")
                
            # 2. Try Sina (AKShare)
            try:
                self.log("[*] Fetching all market data (Sina)...")
                df = ak.stock_zh_a_spot()
                rename_map = {
                    '代码': 'code', '名称': 'name', '最新价': 'current', '涨跌幅': 'change_percent',
                    '昨收': 'prev_close', '成交额': 'amount', '最高': 'high'
                }
                df = df.rename(columns=rename_map)
                # Add missing columns
                for col in ['speed', 'turnover', 'circ_mv']:
                    df[col] = 0.0
                
                for col in ['current', 'change_percent', 'prev_close', 'high']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                return df
            except Exception as e:
                self.log(f"[!] Sina failed: {e}")
            
            # 3. Try Sina JSON API (direct, no akshare)
            try:
                self.log("[*] Fetching all market data (Sina JSON API)...")
                df = self._fetch_sina_market_json()
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                self.log(f"[!] Sina JSON failed: {e}")
            
            # 4. Try Manual EM (Fallback for Proxy Issues)
            try:
                self.log("[*] Fetching all market data (Manual EM)...")
                df = self._fetch_em_spot_manual()
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                self.log(f"[!] Manual EM failed: {e}")

            # 5. Try Tushare (Requires TUSHARE_TOKEN and package installed)
            try:
                self.log("[*] Fetching all market data (Tushare)...")
                df = self._fetch_tushare_spot()
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                self.log(f"[!] Tushare failed: {e}")
                
            return None
        finally:
            # Restore proxy settings
            if old_http: os.environ["HTTP_PROXY"] = old_http
            if old_https: os.environ["HTTPS_PROXY"] = old_https

    def fetch_limit_up_pool(self):
        """Fetch Limit Up Pool"""
        try:
            date_str = datetime.now().strftime("%Y%m%d")
            df = ak.stock_zt_pool_em(date=date_str)
            return df
        except Exception as e:
            self.log(f"[!] Limit Up Pool failed: {e}")
            return None

    def fetch_broken_limit_pool(self):
        """Fetch Broken Limit Pool"""
        try:
            date_str = datetime.now().strftime("%Y%m%d")
            df = ak.stock_zt_pool_zbgc_em(date=date_str)
            return df
        except Exception as e:
            self.log(f"[!] Broken Limit Pool failed: {e}")
            return None

    def fetch_indices(self):
        """Fetch major indices"""
        try:
            url = "http://hq.sinajs.cn/list=sh000001,sz399001,sz399006"
            headers = {"Referer": "http://finance.sina.com.cn"}
            
            with requests.Session() as session:
                session.trust_env = False
                resp = session.get(url, headers=headers, timeout=5)
            
            indices = []
            indices_map = {"sh000001": "上证指数", "sz399001": "深证成指", "sz399006": "创业板指"}
            
            for line in resp.text.split('\n'):
                if not line: continue
                parts = line.split('=')
                if len(parts) < 2: continue
                code = parts[0].split('_')[-1]
                data = parts[1].strip('";').split(',')
                if len(data) < 10: continue
                
                name = indices_map.get(code, code)
                current = float(data[3])
                prev_close = float(data[2])
                amount = float(data[9])
                change = ((current - prev_close) / prev_close) * 100 if prev_close > 0 else 0
                
                indices.append({
                    "name": name,
                    "current": current,
                    "change": round(change, 2),
                    "amount": round(amount / 100000000, 2)
                })
            return indices
        except Exception as e:
            self.log(f"[!] Indices failed: {e}")
            return []

    def fetch_history_data(self, code, days=300):
        """
        Fetch last N days of K-line data from Sina Finance.
        """
        # Ensure code format for Sina (e.g. sh600519)
        code = self._format_code(code)
        
        url = f"https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketData.getKLineData?symbol={code}&scale=240&ma=no&datalen={days}"
        
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            resp = requests.get(url, headers=headers, timeout=5)
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                return data
        except Exception as e:
            self.log(f"[!] History data failed for {code}: {e}")
        
        return []

    def search_stock(self, q):
        """
        Search stock by code/name/pinyin.
        """
        if not q:
            return []
            
        url = "https://searchapi.eastmoney.com/api/suggest/get"
        params = {
            "input": q,
            "type": "14", # Stock
            "token": "D43BF722C8E33BDC906FB84D85E326E8",
            "count": 5
        }
        
        try:
            resp = requests.get(url, params=params, timeout=3)
            resp.encoding = 'utf-8'
            data = resp.json()
            
            if "QuotationCodeTable" in data and "Data" in data["QuotationCodeTable"]:
                results = []
                for item in data["QuotationCodeTable"]["Data"]:
                    market_type = item.get("MarketType")
                    code = item.get("Code")
                    name = item.get("Name")
                    
                    prefix = ""
                    if market_type == "1": prefix = "sh"
                    elif market_type == "2": prefix = "sz"
                    else: continue 
                    
                    full_code = f"{prefix}{code}"
                    results.append({
                        "code": full_code,
                        "name": name,
                        "display_code": code
                    })
                return results
        except Exception as e:
            self.log(f"[!] Search error: {e}")
            
        return []

    def get_stock_info(self, code):
        """
        Get basic stock info (name, concept) for adding to watchlist.
        """
        name = "未知股票"
        concept = "自选"
        
        try:
            # Construct EastMoney secid
            raw_code = self._strip_code(code)
            market = '1' if code.startswith('sh') else '0'
            secid = f"{market}.{raw_code}"
                
            em_url = f"http://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f14,f127"
            resp = requests.get(em_url, timeout=3)
            em_data = resp.json()
            if em_data and em_data.get('data'):
                name = em_data['data'].get('f14', name)
                concept = em_data['data'].get('f127', concept)
        except Exception as e:
            self.log(f"[!] Get stock info error: {e}")
            
        return name, concept

    def _fetch_em_spot_manual(self):
        """
        Manual implementation of EastMoney Spot Data to bypass proxy issues.
        Uses HTTP and disables proxies; smaller page size to reduce load.
        """
        try:
            url = "http://82.push2.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": "1", "pz": "2000", "po": "1", "np": "1", 
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": "2", "invt": "2", "fid": "f3",
                "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
                "fields": "f12,f14,f2,f3,f4,f5,f6,f7,f8,f9,f10,f15,f16,f17,f18,f20,f21,f23,f24,f25,f22,f11,f62,f128,f136,f115,f152"
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "http://quote.eastmoney.com/",
            }
            
            session = requests.Session()
            session.trust_env = False # Ignore system proxy
            
            resp = session.get(url, params=params, headers=headers, timeout=10)
            data = resp.json()
            
            if data and data.get('data') and data['data'].get('diff'):
                rows = data['data']['diff']
                # Convert to DataFrame
                df = pd.DataFrame(rows)
                rename_map = {
                    'f12': 'code', 'f14': 'name', 'f2': 'current', 'f3': 'change_percent',
                    'f8': 'turnover', 'f20': 'circ_mv', 'f18': 'prev_close',
                    'f15': 'high', 'f16': 'low', 'f17': 'open', 'f6': 'amount'
                }
                df = df.rename(columns=rename_map)
                
                for col in ['current', 'change_percent', 'prev_close', 'high', 'amount']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
                return df
        except Exception as e:
            self.log(f"[!] Manual EM fetch failed: {e}")
        return None

    def _fetch_sina_market_json(self):
        """Fallback: use Sina Market_Center JSON API for full market data."""
        url = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getNameList"
        params = {
            "page": 1,
            "num": 5000,
            "sort": "symbol",
            "asc": 1,
            "node": "hs_a",
        }
        headers = {
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        with requests.Session() as session:
            session.trust_env = False
            resp = session.get(url, params=params, headers=headers, timeout=10)
        resp.encoding = 'utf-8'

        # The API returns JSON text; if blocked, text may start with '<'
        text = resp.text.strip()
        if not text or text.startswith('<'):
            raise ValueError("Sina JSON blocked or empty")
        data = json.loads(text)
        if not data:
            return None

        df = pd.DataFrame(data)
        rename_map = {
            'symbol': 'code',
            'name': 'name',
            'trade': 'current',
            'changepercent': 'change_percent',
            'settlement': 'prev_close',
            'high': 'high',
            'amount': 'amount'
        }
        df = df.rename(columns=rename_map)

        # Normalize fields
        for col in ['current', 'change_percent', 'prev_close', 'high', 'amount']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # Add placeholders to align schema
        for col in ['speed', 'turnover', 'circ_mv']:
            df[col] = 0.0

        return df

    def _fetch_tushare_spot(self):
        """Fallback using Tushare daily data. Requires env TUSHARE_TOKEN and tushare installed."""
        try:
            import tushare as ts
        except Exception:
            return None
        token = os.environ.get("TUSHARE_TOKEN", "")
        if not token:
            return None
        ts.set_token(token)
        pro = ts.pro_api(token)
        today = datetime.now().strftime("%Y%m%d")
        try:
            df = pro.daily(trade_date=today)
            if df is None or df.empty:
                return None
            df = df.rename(columns={
                'ts_code': 'code',
                'close': 'current',
                'pct_chg': 'change_percent',
                'pre_close': 'prev_close',
                'high': 'high',
                'amount': 'amount'
            })
            for col in ['current', 'change_percent', 'prev_close', 'high', 'amount']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            # Normalize code to sh/sz
            def _fmt(code):
                if code.endswith('.SH'):
                    return 'sh' + code.split('.')[0]
                if code.endswith('.SZ'):
                    return 'sz' + code.split('.')[0]
                return code
            df['code'] = df['code'].apply(_fmt)
            for col in ['speed', 'turnover', 'circ_mv']:
                df[col] = 0.0
            return df
        except Exception as e:
            self.log(f"[!] Tushare error: {e}")
            return None

# Global instance
data_provider = DataProvider()
