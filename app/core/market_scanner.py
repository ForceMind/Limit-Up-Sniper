import requests
import json
import time
from datetime import datetime
import akshare as ak
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

# 临时过滤北证股票 (8开头, 4开头, 92开头)
FILTER_BSE = False

def is_bse_stock(code):
    """检查是否为北证股票"""
    return code.startswith('8') or code.startswith('4') or code.startswith('92')

def is_20cm_stock(code):
    """检查是否为创业板(30)或科创板(68)"""
    return code.startswith('30') or code.startswith('68')

def scan_intraday_limit_up(logger=None):
    """
    扫描盘中即将涨停的股票 (优先使用 AKShare/EastMoney 接口，带连接修复)
    逻辑:
    1. 涨幅 > 5%
    2. 区分未封板(Intraday)和已封板(LimitUp)
    """
    if logger: logger("[*] 正在扫描盘中异动股 (数据源: AKShare/EastMoney)...")
    # print("[*] 正在扫描盘中异动股 (数据源: AKShare/EastMoney)...")
    
    # 使用 AKShare 的底层接口逻辑 (EastMoney)，但增加 Headers 修复连接问题
    url = "http://push2.eastmoney.com/api/qt/clist/get"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "http://quote.eastmoney.com/"
    }
    params = {
        "pn": 1,
        "pz": 3000, # 获取更多以覆盖全市场活跃股
        "po": 1,
        "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2,
        "invt": 2,
        "fid": "f3", # 按涨幅排序
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048", # 沪深A股
        "fields": "f12,f14,f3,f22,f8,f2,f18,f21", # 代码,名称,涨幅,涨速,换手,现价,昨收,流通市值
        "_": int(time.time() * 1000)
    }
    
    intraday_stocks = []
    sealed_stocks = []
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        data = resp.json()
        if not data.get('data'):
            return [], []
            
        stock_list = data['data']['diff']
        
        for s in stock_list:
            change_percent = s['f3']
            speed = s['f22']
            turnover = s['f8']
            code = s['f12']
            name = s['f14']
            current = s['f2']
            prev_close = s['f18']
            circ_mv = s.get('f21', 0) # 流通市值
            
            # 0. 过滤北证
            if FILTER_BSE and is_bse_stock(code):
                continue
            
            # 0.1 过滤非A股 (如港股)
            if not code.isdigit() or len(code) != 6:
                continue

            # 1. 动态涨幅过滤
            is_20cm = is_20cm_stock(code)
            
            # 计算涨停价
            limit_ratio = 1.2 if is_20cm else 1.1
            limit_up_price = round(prev_close * limit_ratio, 2)
            
            # 格式化代码
            if is_bse_stock(code):
                full_code = f"bj{code}"
            else:
                full_code = f"sh{code}" if code.startswith('6') else f"sz{code}"

            # 检查是否已封板
            # 严格判定: 现价 >= 涨停价 (允许0.01误差)
            # 注意: 实时行情中，如果卖一量为0，通常意味着封死。但 clist 接口不返回卖一量。
            # 我们只能依赖价格判定。
            is_sealed = current >= limit_up_price - 0.01
            
            if is_sealed:
                # 已封板 -> 加入 sealed_stocks
                sealed_stocks.append({
                    "code": full_code,
                    "name": name,
                    "current": current,
                    "change_percent": change_percent,
                    "time": "-", # 实时扫描无法获取准确封板时间
                    "concept": "盘中涨停",
                    "reason": "涨停",
                    "strategy": "LimitUp",
                    "circulation_value": circ_mv,
                    "turnover": turnover
                })
                continue # 不再加入 intraday

            # 未封板 -> 检查是否符合 Intraday 标准
            # 阈值设定:
            if is_20cm:
                if change_percent < 10.0: # 创业板放宽到 10%
                    continue
            else:
                if change_percent < 5.0:
                    continue
                
            # 2. 涨速过滤 (放宽要求，只要涨幅够高，不一定非要正在拉升)
            # 如果涨幅已经很高(>8% 或 >15%)，则忽略涨速要求
            # is_high_position = (is_20cm and change_percent > 15) or (not is_20cm and change_percent > 8)
            
            # if not is_high_position and speed < 0.5:
            #    continue
            
            # 只要涨幅达标，全部纳入观察，不再强制要求涨速 (避免盘后或静默期无数据)
                
            # 3. 排除 ST (名称带ST)
            if 'ST' in name:
                continue
                
            # 格式化代码
            if is_bse_stock(code):
                full_code = f"bj{code}"
            else:
                full_code = f"sh{code}" if code.startswith('6') else f"sz{code}"
            
            intraday_stocks.append({
                "code": full_code,
                "name": name,
                "concept": "盘中异动",
                "reason": f"盘中突击: 涨幅{change_percent}%, 涨速{speed}%",
                "score": 8.0 + (speed * 0.5), # 涨速越快分越高
                "strategy": "LimitUp",
                "circulation_value": circ_mv, # 流通市值
                "turnover": turnover # 换手率
            })
            
            if logger: logger(f"    [+] 发现异动: {name} 涨幅:{change_percent}% 涨速:{speed}%")
            
    except Exception as e:
        if logger: logger(f"[!] 扫描行情失败: {e}")
        
    return intraday_stocks, sealed_stocks

def scan_limit_up_pool(logger=None):
    """
    扫描已涨停的股票 (使用 AKShare/EastMoney 接口，带连接修复)
    尝试获取封板时间
    """
    if logger: logger("[*] 正在扫描已涨停股票 (AKShare/EastMoney)...")
    
    # 尝试使用 EastMoney 的涨停池专用接口 (TopicZtpPool) 获取更详细信息(如封板时间)
    # 接口: http://push2ex.eastmoney.com/getTopicZtpPool
    # 参数: ut=..., dpt=wz.ztzt
    
    url = "http://push2ex.eastmoney.com/getTopicZtpPool"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "http://quote.eastmoney.com/"
    }
    params = {
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "dpt": "wz.ztzt",
        "Pageindex": 0,
        "Pagesize": 200,
        "Sort": "fbt:asc", # 按封板时间排序
        "Date": datetime.now().strftime("%Y%m%d"),
        "_": int(time.time() * 1000)
    }
    
    found_stocks = []
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        data = resp.json()
        if not data.get('data') or not data['data'].get('pool'):
            # Fallback to clist if ZT pool is empty (e.g. morning) or fails
            if logger: logger("[!] 专用涨停接口无数据，尝试通用接口...")
            return scan_limit_up_pool_fallback(logger)
            
        pool_list = data['data']['pool']
        
        for s in pool_list:
            # c: code, n: name, zdp: change_percent, p: current, lbc: limit_up_days
            # fbt: first_seal_time (int, e.g. 93000)
            # lbt: last_seal_time
            # fund: concept string? No, usually hybk
            
            code = s['c']
            name = s['n']
            change_percent = s['zdp']
            current = s['p'] / 1000 if s['p'] > 1000 else s['p'] # Sometimes scaled? No, usually raw. Wait, EM ZT pool usually returns raw.
            # Actually check sample data: p: 1234 -> 12.34? No, usually standard.
            # Let's assume standard.
            
            # Format time
            fbt = str(s['fbt'])
            formatted_time = fbt
            if len(fbt) == 6:
                formatted_time = f"{fbt[:2]}:{fbt[2:4]}:{fbt[4:]}"
            elif len(fbt) == 5:
                formatted_time = f"0{fbt[:1]}:{fbt[1:3]}:{fbt[3:]}"
                
            turnover = s['hs'] # turnover
            circ_mv = s['ltsz'] # circulation value
            limit_days = s['lbc'] # limit up days
            
            # 0. 过滤北证
            if FILTER_BSE and is_bse_stock(code): continue
            
            # 格式化代码
            if is_bse_stock(code):
                full_code = f"bj{code}"
            else:
                full_code = f"sh{code}" if code.startswith('6') else f"sz{code}"
            
            found_stocks.append({
                "code": full_code,
                "name": name,
                "current": current,
                "change_percent": change_percent,
                "time": formatted_time,
                "concept": s.get('hybk', '-'), # Industry
                "reason": f"{limit_days}连板" if limit_days > 1 else "首板",
                "strategy": "LimitUp",
                "circulation_value": circ_mv,
                "turnover": turnover,
                "limit_up_days": limit_days
            })
            
    except Exception as e:
        if logger: logger(f"[!] 专用涨停接口失败 ({e})，切换通用接口...")
        return scan_limit_up_pool_fallback(logger)
        
    return found_stocks

def scan_limit_up_pool_fallback(logger=None):
    """
    备用: 使用通用 clist 接口扫描涨停 (无封板时间)
    """
    # if logger: logger("[*] 正在扫描已涨停股票 (Fallback)...")
    
    url = "http://push2.eastmoney.com/api/qt/clist/get"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "http://quote.eastmoney.com/"
    }
    params = {
        "pn": 1,
        "pz": 2000, 
        "po": 1,
        "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2,
        "invt": 2,
        "fid": "f3", 
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048", 
        "fields": "f12,f14,f3,f2,f18,f8,f21", 
        "_": int(time.time() * 1000)
    }
    
    found_stocks = []
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        data = resp.json()
        if not data.get('data'):
            return []
            
        stock_list = data['data']['diff']
        
        for s in stock_list:
            change_percent = s['f3']
            current = s['f2']
            prev_close = s['f18']
            code = s['f12']
            name = s['f14']
            turnover = s['f8']
            circ_mv = s.get('f21', 0)
            
            if FILTER_BSE and is_bse_stock(code): continue
            if not code.isdigit() or len(code) != 6: continue
                
            is_20cm = is_20cm_stock(code)
            is_30cm = is_bse_stock(code)
            limit_ratio = 1.1
            if is_20cm: limit_ratio = 1.2
            if is_30cm: limit_ratio = 1.3
            limit_up_price = round(prev_close * limit_ratio, 2)
            
            if current < limit_up_price - 0.01: continue
            if change_percent < 0: continue

            if is_bse_stock(code):
                full_code = f"bj{code}"
            else:
                full_code = f"sh{code}" if code.startswith('6') else f"sz{code}"
            
            found_stocks.append({
                "code": full_code,
                "name": name,
                "current": current,
                "change_percent": change_percent,
                "time": "-", 
                "concept": "-", 
                "reason": "涨停",
                "strategy": "LimitUp",
                "circulation_value": circ_mv,
                "turnover": turnover
            })
            
    except Exception as e:
        if logger: logger(f"[!] 扫描涨停池失败: {e}")
        return []
        
    return found_stocks


def scan_broken_limit_pool(logger=None):
    """
    扫描炸板股票 (使用 AKShare 接口)
    """
    # if logger: logger("[*] 正在扫描炸板股票 (AKShare)...")
    
    found_stocks = []
    try:
        # 使用 AKShare 获取炸板股池
        df = ak.stock_zt_pool_zbgc_em(date=datetime.now().strftime("%Y%m%d"))
        
        if df is None or df.empty:
            return []
            
        for _, row in df.iterrows():
            code = str(row['代码'])
            name = str(row['名称'])
            change_percent = round(float(row['涨跌幅']), 2)
            current = round(float(row['最新价']), 2)
            high = round(float(row['涨停价']), 2)
            turnover = round(float(row['换手率']), 2) if '换手率' in row else 0
            circ_mv = float(row['流通市值']) if '流通市值' in row else 0
            
            if FILTER_BSE and is_bse_stock(code): continue
            if 'ST' in name: continue
            
            if is_bse_stock(code):
                full_code = f"bj{code}"
            else:
                full_code = f"sh{code}" if code.startswith('6') else f"sz{code}"
            
            # Format time: 102530 -> 10:25:30
            raw_time = str(row['首次封板时间'])
            formatted_time = raw_time
            if len(raw_time) == 6:
                formatted_time = f"{raw_time[:2]}:{raw_time[2:4]}:{raw_time[4:]}"
            elif len(raw_time) == 5: # 93000
                formatted_time = f"0{raw_time[:1]}:{raw_time[1:3]}:{raw_time[3:]}"
            
            found_stocks.append({
                "code": full_code,
                "name": name,
                "current": current,
                "change_percent": change_percent,
                "time": formatted_time, 
                "high": high,
                "concept": str(row['所属行业']),
                "associated": "-",
                "amplitude": round(float(row['振幅']), 2) if '振幅' in row else 0,
                "circulation_value": circ_mv,
                "turnover": turnover
            })
    except Exception as e:
        if logger: logger(f"[!] 扫描炸板池失败: {e}")
        
    return found_stocks

def scan_broken_limit_pool_fallback(logger=None):
    """备用: 直接调用新的 scan_broken_limit_pool"""
    return scan_broken_limit_pool(logger)

def scan_limit_up_pool_fallback(logger=None):
    """备用: 直接调用新的 scan_limit_up_pool"""
    return scan_limit_up_pool(logger)

def get_market_overview(logger=None):
    """
    获取大盘情绪数据: 指数、成交量、涨跌家数、涨停炸板数
    """
    overview = {
        "indices": [],
        "stats": {
            "limit_up_count": 0,
            "limit_down_count": 0,
            "broken_count": 0,
            "up_count": 0,
            "down_count": 0,
            "flat_count": 0,
            "total_volume": 0, # 亿
            "sentiment": "Neutral",
            "suggestion": "观察"
        }
    }
    
    # 1. 获取指数数据 (新浪)
    try:
        url = "http://hq.sinajs.cn/list=sh000001,sz399001,sz399006"
        headers = {"Referer": "http://finance.sina.com.cn"}
        resp = requests.get(url, headers=headers, timeout=3)
        content = resp.text
        
        # 解析
        # var hq_str_sh000001="上证指数,open,prev_close,current,high,low,buy,sell,vol,amount,..."
        indices_map = {
            "sh000001": "上证指数",
            "sz399001": "深证成指",
            "sz399006": "创业板指"
        }
        
        total_amount = 0
        
        for line in content.split('\n'):
            if not line: continue
            parts = line.split('=')
            if len(parts) < 2: continue
            
            code = parts[0].split('_')[-1]
            data = parts[1].strip('";').split(',')
            if len(data) < 10: continue
            
            name = indices_map.get(code, code)
            current = float(data[3])
            prev_close = float(data[2])
            amount = float(data[9]) # 成交额 (元)
            
            change = 0
            if prev_close > 0:
                change = ((current - prev_close) / prev_close) * 100
                
            overview["indices"].append({
                "name": name,
                "current": current,
                "change": round(change, 2),
                "amount": round(amount / 100000000, 2) # 亿
            })
            
            total_amount += amount
            
        overview["stats"]["total_volume"] = round(total_amount / 100000000, 0) # 总成交额(亿)
        
    except Exception as e:
        if logger: logger(f"[!] 获取指数失败: {e}")

    # 2. 获取涨跌分布 (东财全A扫描 - 并发分页获取)
    try:
        url = "http://push2.eastmoney.com/api/qt/clist/get"
        base_params = {
            "pn": 1,
            "pz": 3000, # Increase page size to reduce requests
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", # 沪深A股
            "fields": "f3", # 只取涨跌幅
            "_": int(time.time() * 1000)
        }
        
        up = 0
        down = 0
        flat = 0
        limit_down = 0
        
        def fetch_page(page):
            params = base_params.copy()
            params["pn"] = page
            try:
                resp = requests.get(url, params=params, timeout=10) # Increase timeout to 10s
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('data') and data['data'].get('diff'):
                        return data['data']['diff']
            except Exception as e:
                if logger: logger(f"[!] Fetch page {page} failed: {e}")
            return []

        # 并发抓取 2 页 (覆盖约 6000 只股票)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(fetch_page, page) for page in range(1, 3)]
            for future in as_completed(futures):
                stocks = future.result()
                if not stocks: continue # Skip empty results
                for s in stocks:
                    chg = s.get('f3')
                    if chg is None: continue
                    
                    if chg > 0:
                        up += 1
                    elif chg < 0:
                        down += 1
                        # 粗略估算跌停: < -9.5%
                        if chg < -9.5:
                            limit_down += 1
                    else:
                        flat += 1
        
        # Only update if we got some data
        if up + down + flat > 0:
            overview["stats"]["up_count"] = up
            overview["stats"]["down_count"] = down
            overview["stats"]["flat_count"] = flat
            overview["stats"]["limit_down_count"] = limit_down
            
    except Exception as e:
        if logger: logger(f"[!] 获取涨跌分布失败: {e}")

    # 3. 获取涨停/炸板数据 (东财)
    try:
        # 直接使用通用接口获取数据，不再尝试失效的专用接口
        zt_list = scan_limit_up_pool(logger)
        if zt_list is not None:
            overview["stats"]["limit_up_count"] = len(zt_list)
        
        zb_list = scan_broken_limit_pool(logger)
        if zb_list is not None:
            overview["stats"]["broken_count"] = len(zb_list)
            
    except Exception as e:
        if logger: logger(f"[!] 获取涨停统计失败: {e}")
        
    # 3. 计算情绪和建议
    # 逻辑:
    # 情绪: 
    #   High: 涨停 > 50 且 指数 > 0
    #   Low: 指数 < -1% 或 涨停 < 20
    #   Neutral: 其他
    
    zt_count = overview["stats"]["limit_up_count"]
    sh_change = 0
    for idx in overview["indices"]:
        if idx["name"] == "上证指数":
            sh_change = idx["change"]
            break
            
    sentiment = "Neutral"
    suggestion = "观察"
    
    if zt_count > 50 and sh_change > -0.5:
        sentiment = "High"
        suggestion = "积极打板"
    elif zt_count < 20 or sh_change < -1.0:
        sentiment = "Low"
        suggestion = "谨慎出手"
    else:
        sentiment = "Neutral"
        suggestion = "去弱留强"
        
    # 特殊情况: 放量大跌
    if sh_change < -1.5 and overview["stats"]["total_volume"] > 10000:
        sentiment = "Panic"
        suggestion = "空仓避险"
        
    overview["stats"]["sentiment"] = sentiment
    overview["stats"]["suggestion"] = suggestion
    
    return overview
