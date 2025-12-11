import requests
import json
import time
from datetime import datetime

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
    扫描盘中即将涨停的股票 (基于东方财富实时行情)
    逻辑:
    1. 涨幅 > 5% 且 < 9.8% (未封板)
    2. 涨速 > 1% (1分钟内快速拉升)
    3. 换手率 > 3% (有一定流动性)
    """
    if logger: logger("[*] 正在扫描盘中异动股 (数据源: 东方财富)...")
    print("[*] 正在扫描盘中异动股 (数据源: 东方财富)...")
    
    url = "http://82.push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": 1,
        "pz": 200, # 取前200名，避免前50名全是已涨停的股票导致漏掉接近涨停的
        "po": 1,
        "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2,
        "invt": 2,
        "fid": "f3", # 按涨幅排序
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048", # 沪深A股
        "fields": "f12,f14,f3,f22,f8,f2,f18", # 代码,名称,涨幅,涨速,换手,现价,昨收
        "_": int(time.time() * 1000)
    }
    
    found_stocks = []
    
    try:
        resp = requests.get(url, params=params, timeout=5)
        data = resp.json()
        if not data.get('data'):
            return []
            
        stock_list = data['data']['diff']
        
        for s in stock_list:
            change_percent = s['f3']
            speed = s['f22']
            turnover = s['f8']
            code = s['f12']
            name = s['f14']
            current = s['f2']
            prev_close = s['f18']
            
            # 0. 过滤北证
            if FILTER_BSE and is_bse_stock(code):
                continue

            # 1. 动态涨幅过滤
            is_20cm = is_20cm_stock(code)
            
            # 计算涨停价
            limit_ratio = 1.2 if is_20cm else 1.1
            limit_up_price = round(prev_close * limit_ratio, 2)
            
            # 过滤已封板的股票 (现价 >= 涨停价)
            if current >= limit_up_price - 0.01:
                continue

            # 阈值设定:
            # 10cm: > 5%
            # 20cm: > 10%
            if is_20cm:
                if change_percent < 10.0:
                    continue
            else:
                if change_percent < 5.0:
                    continue
                
            # 2. 涨速过滤 (放宽要求，只要涨幅够高，不一定非要正在拉升)
            # 如果涨幅已经很高(>8% 或 >15%)，则忽略涨速要求
            is_high_position = (is_20cm and change_percent > 15) or (not is_20cm and change_percent > 8)
            
            if not is_high_position and speed < 0.5:
                continue
                
            # 3. 排除 ST (名称带ST)
            if 'ST' in name:
                continue
                
            # 格式化代码
            if is_bse_stock(code):
                full_code = f"bj{code}"
            else:
                full_code = f"sh{code}" if code.startswith('6') else f"sz{code}"
            
            found_stocks.append({
                "code": full_code,
                "name": name,
                "concept": "盘中异动",
                "reason": f"盘中突击: 涨幅{change_percent}%, 涨速{speed}%",
                "score": 8.0 + (speed * 0.5), # 涨速越快分越高
                "strategy": "LimitUp"
            })
            
            if logger: logger(f"    [+] 发现异动: {name} 涨幅:{change_percent}% 涨速:{speed}%")
            
    except Exception as e:
        if logger: logger(f"[!] 扫描行情失败: {e}")
        
    return found_stocks

def scan_limit_up_pool(logger=None):
    """
    扫描已涨停的股票 (使用东方财富 clist 接口)
    """
    if logger: logger("[*] 正在扫描已涨停股票...")
    
    # 使用 clist 接口作为主接口
    url = "http://push2.eastmoney.com/api/qt/clist/get"
    
    params = {
        "pn": 1,
        "pz": 200, # Top 200
        "po": 1,
        "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2,
        "invt": 2,
        "fid": "f3", # 按涨幅排序
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048", # 沪深A股
        "fields": "f12,f14,f3,f2,f100,f18,f15", # Code, Name, Change, Current, Industry, PrevClose, High
        "_": int(time.time() * 1000)
    }
    
    found_stocks = []
    
    try:
        resp = requests.get(url, params=params, timeout=5)
        data = resp.json()
        if not data.get('data'):
            return []
            
        stock_list = data['data']['diff']
        
        for s in stock_list:
            change_percent = s['f3']
            code = s['f12']
            name = s['f14']
            current = s['f2']
            prev_close = s['f18']
            high = s['f15']
            
            # 0. 过滤北证
            if FILTER_BSE and is_bse_stock(code):
                continue
            
            # 排除 ST
            if 'ST' in name:
                continue
                
            # 1. 涨停判断
            is_20cm = is_20cm_stock(code)
            limit_ratio = 1.2 if is_20cm else 1.1
            limit_up_price = round(prev_close * limit_ratio, 2)
            
            # print(f"DEBUG: {name} {current} {high} {limit_up_price}")
            
            # 允许 0.01 的误差
            if current < limit_up_price - 0.01:
                continue
                
            # 如果当前价格低于最高价，说明炸板了，不应在涨停池中
            if current < high:
                continue
                
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
                "speed": 0, 
                "time": "-", # 无法获取首封时间
                "concept": s.get('f100', '-'), 
                "associated": "-" 
            })
            
    except Exception as e:
        if logger: logger(f"[!] 扫描涨停池失败: {e}")
        
    return found_stocks

def scan_broken_limit_pool(logger=None):
    """
    扫描炸板股票 (使用 clist 接口计算)
    """
    # if logger: logger("[*] 正在扫描炸板股票...")
    
    url = "http://push2.eastmoney.com/api/qt/clist/get"
    
    params = {
        "pn": 1,
        "pz": 200, # Top 200
        "po": 1,
        "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2,
        "invt": 2,
        "fid": "f3", 
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
        "fields": "f12,f14,f3,f2,f15,f18,f100,f16", # Code, Name, Change, Current, High, PrevClose, Industry, Low
        "_": int(time.time() * 1000)
    }
    
    found_stocks = []
    try:
        resp = requests.get(url, params=params, timeout=5)
        data = resp.json()
        if not data.get('data'):
            return []
            
        stock_list = data['data']['diff']
        for s in stock_list:
            code = s['f12']
            name = s['f14']
            change_percent = s['f3']
            current = s['f2']
            high = s['f15']
            prev_close = s['f18']
            
            if FILTER_BSE and is_bse_stock(code): continue
            if 'ST' in name: continue
            
            # Calculate Limit Up Price
            is_20cm = is_20cm_stock(code)
            limit_ratio = 1.2 if is_20cm else 1.1
            limit_up_price = round(prev_close * limit_ratio, 2)
            
            # Check if High reached Limit Up (approx)
            if high >= limit_up_price - 0.01:
                # Check if Broken (Current < High)
                # Use a small epsilon to avoid floating point issues
                if current < high - 0.009:
                    if is_bse_stock(code):
                        full_code = f"bj{code}"
                    else:
                        full_code = f"sh{code}" if code.startswith('6') else f"sz{code}"
                    
                    found_stocks.append({
                        "code": full_code,
                        "name": name,
                        "current": current,
                        "change_percent": change_percent,
                        "time": "-", # 无法获取炸板时间
                        "high": high,
                        "concept": s.get('f100', '-'),
                        "associated": "-",
                        "amplitude": round(((high - s.get('f16', 0)) / prev_close) * 100, 2) if s.get('f16') else 0
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

    # 2. 获取涨停/炸板数据 (东财)
    try:
        # 直接使用通用接口获取数据，不再尝试失效的专用接口
        zt_list = scan_limit_up_pool(logger)
        overview["stats"]["limit_up_count"] = len(zt_list)
        
        zb_list = scan_broken_limit_pool(logger)
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
