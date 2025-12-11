from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, BackgroundTasks, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import requests
import json
import os
import asyncio
import time
from typing import List, Optional
from pydantic import BaseModel
from news_analyzer import generate_watchlist, analyze_single_stock
from market_scanner import scan_limit_up_pool, scan_broken_limit_pool, get_market_overview
from stock_utils import calculate_metrics

app = FastAPI()

templates = Jinja2Templates(directory="templates")

# WebSocket Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

def load_watchlist():
    """加载复盘生成的关注列表"""
    if os.path.exists("watchlist.json"):
        try:
            with open("watchlist.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

# 全局变量
watchlist_data = load_watchlist()
watchlist_map = {item['code']: item for item in watchlist_data}
WATCH_LIST = list(watchlist_map.keys())
limit_up_pool_data = []
broken_limit_pool_data = []

def load_market_pools():
    global limit_up_pool_data, broken_limit_pool_data
    if os.path.exists("market_pools.json"):
        try:
            with open("market_pools.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                limit_up_pool_data = data.get("limit_up", [])
                broken_limit_pool_data = data.get("broken", [])
        except:
            pass

def save_market_pools():
    try:
        with open("market_pools.json", "w", encoding="utf-8") as f:
            json.dump({
                "limit_up": limit_up_pool_data,
                "broken": broken_limit_pool_data,
                "updated_at": time.time()
            }, f, ensure_ascii=False)
    except:
        pass

# Load on startup
load_market_pools()

async def update_market_pools_task():
    global limit_up_pool_data, broken_limit_pool_data
    loop = asyncio.get_event_loop()
    while True:
        try:
            # Run blocking IO in executor
            new_limit_up = await loop.run_in_executor(None, scan_limit_up_pool)
            if new_limit_up:
                limit_up_pool_data = new_limit_up
            
            new_broken = await loop.run_in_executor(None, scan_broken_limit_pool)
            if new_broken:
                broken_limit_pool_data = new_broken
                
            await loop.run_in_executor(None, save_market_pools)
        except Exception as e:
            print(f"Pool update error: {e}")
        
        await asyncio.sleep(10) # Update every 10 seconds

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(update_market_pools_task())

if not WATCH_LIST:
    WATCH_LIST = ['sh600519', 'sz002405', 'sz300059']

def refresh_watchlist():
    """刷新全局监控列表"""
    global watchlist_data, watchlist_map, WATCH_LIST
    watchlist_data = load_watchlist()
    watchlist_map = {item['code']: item for item in watchlist_data}
    WATCH_LIST = list(watchlist_map.keys())
    if not WATCH_LIST:
        WATCH_LIST = ['sh600519', 'sz002405', 'sz300059']

@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text() # Keep connection open
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/api/search")
async def search_stock(q: str):
    """
    搜索股票 (支持代码、拼音、名称)
    使用东方财富接口
    """
    if not q:
        return []
        
    url = "https://searchapi.eastmoney.com/api/suggest/get"
    params = {
        "input": q,
        "type": "14", # 股票
        "token": "D43BF722C8E33BDC906FB84D85E326E8",
        "count": 5
    }
    
    try:
        resp = requests.get(url, params=params, timeout=3)
        data = resp.json()
        if "QuotationCodeTable" in data and "Data" in data["QuotationCodeTable"]:
            results = []
            for item in data["QuotationCodeTable"]["Data"]:
                # item: { "Code": "600519", "Name": "贵州茅台", "PinYin": "GZMT", "MarketType": "1" ... }
                # MarketType: 1=SH, 2=SZ
                market_type = item.get("MarketType")
                code = item.get("Code")
                name = item.get("Name")
                
                prefix = ""
                if market_type == "1": prefix = "sh"
                elif market_type == "2": prefix = "sz"
                else: continue # 忽略其他市场
                
                full_code = f"{prefix}{code}"
                results.append({
                    "code": full_code,
                    "name": name,
                    "display_code": code
                })
            return results
    except Exception as e:
        print(f"Search error: {e}")
        
    return []

@app.post("/api/add_stock")
async def add_stock(code: str):
    """手动添加股票到监控列表"""
    global watchlist_data, watchlist_map, WATCH_LIST
    
    code = code.lower().strip()
    
    # 自动补全前缀
    if len(code) == 6 and code.isdigit():
        if code.startswith('6'):
            code = f"sh{code}"
        elif code.startswith('0') or code.startswith('3'):
            code = f"sz{code}"
        else:
            # 默认为 sh (或者报错)
            pass
    
    # 简单的格式校验
    if not (code.startswith('sh') or code.startswith('sz')):
        return {"status": "error", "message": "Invalid code format"}
        
    # 如果已存在，忽略
    if code in watchlist_map:
        return {"status": "success", "message": "Already exists"}
        
    # 计算高级指标
    metrics = calculate_metrics(code)
    
    # 获取股票详细信息 (名称 + 行业/概念)
    name = "手动添加"
    concept = "自选"
    
    try:
        # 构造 EastMoney secid
        # sh -> 1.xxx, sz -> 0.xxx
        secid = ""
        if code.startswith('sh'):
            secid = f"1.{code[2:]}"
        else:
            secid = f"0.{code[2:]}"
            
        em_url = f"http://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f14,f127"
        resp = requests.get(em_url, timeout=3)
        em_data = resp.json()
        if em_data and em_data.get('data'):
            name = em_data['data'].get('f14', name)
            concept = em_data['data'].get('f127', concept)
    except Exception as e:
        print(f"Error fetching stock info: {e}")
    
    # 添加新股票
    new_item = {
        "code": code,
        "name": name, 
        "news_summary": "Manual Add",
        "concept": concept,
        "initial_score": 5, # 默认中等分数
        "strategy_type": "Manual",
        "seal_rate": metrics['seal_rate'],
        "broken_rate": metrics['broken_rate'],
        "next_day_premium": metrics['next_day_premium'],
        "limit_up_days": metrics['limit_up_days']
    }
    
    watchlist_data.append(new_item)
    watchlist_map[code] = new_item
    if code not in WATCH_LIST:
        WATCH_LIST.append(code)
        
    # 保存到文件
    try:
        with open("watchlist.json", "w", encoding="utf-8") as f:
            json.dump(watchlist_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving watchlist: {e}")
        
    return {"status": "success"}

# 使用全局 Queue 来传递日志
import queue
log_queue = queue.Queue()

async def log_broadcaster():
    """从队列读取日志并广播"""
    while True:
        try:
            # 非阻塞获取
            msg = log_queue.get_nowait()
            await manager.broadcast(msg)
        except queue.Empty:
            await asyncio.sleep(0.1)

def update_limit_up_pool_task():
    """更新已涨停股票池"""
    global limit_up_pool_data
    try:
        # Scan
        pool = scan_limit_up_pool()
        
        enriched_pool = []
        for stock in pool:
            code = stock['code']
            
            # Calculate metrics (Historical)
            metrics = calculate_metrics(code)
            
            # Check watchlist for reason
            reason = "市场强势涨停"
            if code in watchlist_map:
                reason = watchlist_map[code].get('news_summary', '自选股涨停')
            
            stock['seal_rate'] = metrics['seal_rate']
            stock['broken_rate'] = metrics['broken_rate']
            stock['next_day_premium'] = metrics['next_day_premium']
            stock['limit_up_days'] = metrics['limit_up_days']
            stock['reason'] = reason
            # Ensure concept and associated are present (from scanner)
            if 'concept' not in stock:
                stock['concept'] = '-'
            if 'associated' not in stock:
                stock['associated'] = '-'
            
            enriched_pool.append(stock)
            
        limit_up_pool_data = enriched_pool
    except Exception as e:
        print(f"Error updating limit up pool: {e}")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(log_broadcaster())
    # Start background scheduler
    asyncio.create_task(scheduler_loop())
    
    # 启动时立即执行一次盘中扫描，确保列表不为空
    print("Startup: Running initial intraday scan...")
    asyncio.create_task(run_initial_scan())

async def run_initial_scan():
    """启动时立即运行一次扫描"""
    try:
        # 等待几秒确保其他组件就绪
        await asyncio.sleep(2)
        await asyncio.to_thread(execute_analysis, "intraday")
        print("Startup: Initial scan completed.")
    except Exception as e:
        print(f"Startup scan error: {e}")

async def scheduler_loop():
    """Background scheduler for periodic tasks"""
    print("Starting background scheduler...")
    last_analysis_time = 0
    last_pool_update_time = 0
    
    while True:
        current_time = time.time()
        
        # Task 1: Intraday Analysis (Every 60 seconds)
        if current_time - last_analysis_time >= 60:
            # Only run during trading hours (approx check)
            # For simplicity, we run it always or check time
            # Here we just run it.
            try:
                thread_logger(">>> 自动触发盘中突击分析...")
                # Run in thread pool to avoid blocking async loop
                await asyncio.to_thread(execute_analysis, "intraday")
                last_analysis_time = current_time
            except Exception as e:
                print(f"Scheduler error: {e}")
        
        # Task 2: Refresh Quotes (Every 3 seconds)
        # Since frontend polls /api/stocks, we don't strictly need this for data flow,
        # but user asked for "backend to refresh".
        # We can fetch and broadcast to WS to be "real-time push"
        try:
            # Fetch data
            stocks = await asyncio.to_thread(get_stock_quotes)
            # Broadcast if needed (optional, but good for real-time)
            # await manager.broadcast(json.dumps({"type": "quotes", "data": stocks}))
        except Exception as e:
            pass
            
        # Task 3: Update Limit Up Pool (Every 30 seconds)
        # Use a timestamp check instead of modulo to be more reliable
        if current_time - last_pool_update_time >= 30:
             await asyncio.to_thread(update_limit_up_pool_task)
             last_pool_update_time = current_time

        await asyncio.sleep(3)

def thread_logger(msg):
    """线程安全的 logger"""
    log_queue.put(msg)

@app.post("/api/analyze")
async def run_analysis(background_tasks: BackgroundTasks, mode: str = Query("after_hours")):
    """触发复盘分析"""
    # 在后台运行，不阻塞 API
    background_tasks.add_task(execute_analysis, mode)
    return {"status": "success", "message": f"{mode} analysis started in background"}

def execute_analysis(mode="after_hours"):
    try:
        mode_name = "盘后复盘" if mode == "after_hours" else "盘中突击"
        thread_logger(f">>> 开始执行{mode_name}任务...")
        generate_watchlist(logger=thread_logger, mode=mode)
        refresh_watchlist()
        thread_logger(f">>> {mode_name}任务完成，列表已更新。")
    except Exception as e:
        thread_logger(f"!!! 分析任务出错: {e}")
        print(f"Analysis Error: {e}")


def get_tencent_data(codes):
    """
    从腾讯财经接口抓取数据 (作为备用)
    接口格式: http://qt.gtimg.cn/q=sh600519,sz000001
    """
    if not codes:
        return []
        
    url = "http://qt.gtimg.cn/q=" + ",".join(codes)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    stocks = []
    try:
        response = requests.get(url, headers=headers, timeout=3)
        # 腾讯通常返回 GBK
        response.encoding = 'gbk'
        content = response.text.strip()
        
        lines = content.split(';')
        for line in lines:
            if not line or '=' not in line:
                continue
                
            # v_sh600519="1~贵州茅台~600519~1700.00~..."
            parts = line.split('=')
            code_part = parts[0]
            data_str = parts[1].strip('"')
            
            code = code_part.split('_')[-1] # sh600519
            
            data = data_str.split('~')
            if len(data) < 30:
                continue
                
            # 腾讯数据映射
            # 1: 名字, 3: 当前价, 4: 昨收, 5: 开盘, 31: 涨跌, 32: 涨跌幅, 33: 最高, 34: 最低
            name = data[1]
            current_price = float(data[3])
            prev_close = float(data[4])
            open_price = float(data[5])
            high_price = float(data[33])
            # low_price = float(data[34])
            
            change_percent = float(data[32])
            
            limit_up_price = round(prev_close * 1.1, 2) # 简略计算
            
            strategy_info = watchlist_map.get(code, {})
            
            stock_info = {
                "code": code,
                "name": name,
                "current": current_price,
                "change_percent": change_percent,
                "high": high_price,
                "open": open_price,
                "prev_close": prev_close,
                "limit_up_price": limit_up_price,
                "is_limit_up": current_price >= limit_up_price and current_price > 0,
                "strategy": strategy_info.get("strategy_type", "Neutral"),
                "initial_score": strategy_info.get("initial_score", 0),
                "concept": strategy_info.get("concept", "-"),
                "seal_rate": strategy_info.get("seal_rate", 0),
                "broken_rate": strategy_info.get("broken_rate", 0),
                "next_day_premium": strategy_info.get("next_day_premium", 0),
                "limit_up_days": strategy_info.get("limit_up_days", 0)
            }
            stocks.append(stock_info)
            
    except Exception as e:
        print(f"Tencent API Error: {e}")
        
    return stocks

def get_eastmoney_data(codes):
    """
    从东方财富接口抓取数据 (最稳定，支持所有板块)
    """
    if not codes:
        return []
        
    # 构造 secids
    # sh -> 1.xxx, sz -> 0.xxx, bj -> 0.xxx
    secids = []
    code_map = {} # secid -> original_code
    
    for code in codes:
        raw_code = code.replace('sh', '').replace('sz', '').replace('bj', '')
        market = '1' if code.startswith('sh') else '0'
        secid = f"{market}.{raw_code}"
        secids.append(secid)
        code_map[secid] = code
        
    # 分批请求，每次最多 100 个
    stocks = []
    batch_size = 90
    
    for i in range(0, len(secids), batch_size):
        batch = secids[i:i+batch_size]
        url = "http://push2.eastmoney.com/api/qt/ulist/get"
        params = {
            "secids": ",".join(batch),
            "fields": "f12,f14,f2,f3,f4,f18,f15,f16,f17,f139", # 代码,名称,现价,涨幅,涨跌,昨收,最高,最低,开盘,市场
            "invt": 2,
            "fltt": 2,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "_": int(time.time() * 1000)
        }
        
        try:
            resp = requests.get(url, params=params, timeout=5)
            data = resp.json()
            if not data.get('data') or not data['data'].get('diff'):
                continue
                
            for item in data['data']['diff']:
                # item: { "f12": "600519", "f14": "贵州茅台", ... }
                # Need to map back to original code (sh/sz/bj)
                # EastMoney returns f139 (market type)? 
                # f139: 1=SH, 0=SZ/BJ
                
                raw_code = item['f12']
                # Try to find matching code in our list
                # Simple heuristic: check if sh{raw_code}, sz{raw_code}, bj{raw_code} is in codes
                
                # Better: use the secid we sent? 
                # The response doesn't strictly return secid.
                
                # Reconstruct code
                found_code = None
                # Check watchlist map keys
                if f"sh{raw_code}" in watchlist_map: found_code = f"sh{raw_code}"
                elif f"sz{raw_code}" in watchlist_map: found_code = f"sz{raw_code}"
                elif f"bj{raw_code}" in watchlist_map: found_code = f"bj{raw_code}"
                
                if not found_code:
                    continue
                    
                current_price = item['f2']
                if current_price == '-': current_price = 0
                
                prev_close = item['f18']
                if prev_close == '-': prev_close = 0
                
                change_percent = item['f3']
                if change_percent == '-': change_percent = 0
                
                # Calculate Limit Up
                limit_up_price = round(prev_close * 1.1, 2) # Approx
                
                strategy_info = watchlist_map.get(found_code, {})
                
                stock_info = {
                    "code": found_code,
                    "name": item['f14'],
                    "current": current_price,
                    "change_percent": change_percent,
                    "high": item['f15'],
                    "open": item['f17'],
                    "prev_close": prev_close,
                    "limit_up_price": limit_up_price,
                    "is_limit_up": current_price >= limit_up_price - 0.01 and change_percent > 0,
                    "strategy": strategy_info.get("strategy_type", "Neutral"),
                    "initial_score": strategy_info.get("initial_score", 0),
                    "concept": strategy_info.get("concept", "-"),
                    "seal_rate": strategy_info.get("seal_rate", 0),
                    "broken_rate": strategy_info.get("broken_rate", 0),
                    "next_day_premium": strategy_info.get("next_day_premium", 0),
                    "limit_up_days": strategy_info.get("limit_up_days", 0)
                }
                stocks.append(stock_info)
                
        except Exception as e:
            print(f"EastMoney Quote Error: {e}")
            
    return stocks

def get_stock_quotes():
    """
    获取股票行情，优先使用东方财富 (最全)，其次新浪
    """
    # 1. 尝试东方财富
    try:
        em_data = get_eastmoney_data(WATCH_LIST)
        if len(em_data) >= len(WATCH_LIST) * 0.8:
            return em_data
    except Exception as e:
        print(f"EastMoney source failed: {e}")

    # 2. 尝试新浪
    try:
        sina_data = get_sina_data()
        # 简单验证数据完整性
        if len(sina_data) >= len(WATCH_LIST) * 0.8: # 至少获取了80%的数据
            return sina_data
    except Exception as e:
        print(f"Sina source failed: {e}")
        
    # 3. 尝试腾讯 (作为补充或备用)
    print("Switching to Tencent data source...")
    return get_tencent_data(WATCH_LIST)

def get_sina_data():
    """
    从新浪财经接口抓取数据并清洗
    """
    if not WATCH_LIST:
        return []
        
    # 新浪接口一次最多支持约80-100个代码，如果列表过长需要分批，这里暂不处理
    url = "http://hq.sinajs.cn/list=" + ",".join(WATCH_LIST)
    headers = {
        "Referer": "http://finance.sina.com.cn",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    stocks = []
    try:
        response = requests.get(url, headers=headers, timeout=3)
        # 新浪接口通常返回 GBK 编码
        response.encoding = 'gbk'
        content = response.text.strip()
        
        # 解析每一行数据
        lines = content.split('\n')
        for line in lines:
            if not line:
                continue
                
            # 格式: var hq_str_sh600519="贵州茅台,..."
            parts = line.split('=')
            if len(parts) < 2:
                continue
                
            code = parts[0].split('_')[-1] # 获取股票代码，如 sh600519
            data_str = parts[1].strip('";')
            
            if not data_str:
                continue
                
            data = data_str.split(',')
            
            # 确保数据字段足够
            if len(data) < 30:
                continue
                
            # 提取字段
            name = data[0]
            open_price = float(data[1])
            prev_close = float(data[2])
            current_price = float(data[3])
            high_price = float(data[4])
            low_price = float(data[5])
            
            # 如果停牌或未开盘，当前价格可能为0，取昨收
            if current_price == 0:
                current_price = prev_close

            # 计算涨跌幅
            if prev_close > 0:
                change_percent = ((current_price - prev_close) / prev_close) * 100
            else:
                change_percent = 0.0
            
            # 计算粗略涨停价 (昨收 * 1.1)
            limit_up_price = round(prev_close * 1.1, 2)
            
            # 获取策略信息
            strategy_info = watchlist_map.get(code, {})
            
            stock_info = {
                "code": code,
                "name": name,
                "current": current_price,
                "change_percent": round(change_percent, 2),
                "high": high_price,
                "open": open_price,
                "prev_close": prev_close,
                "limit_up_price": limit_up_price,
                "is_limit_up": current_price >= limit_up_price,
                # 注入策略数据
                "strategy": strategy_info.get("strategy_type", "Neutral"),
                "initial_score": strategy_info.get("initial_score", 0),
                "concept": strategy_info.get("concept", "-"),
                # 注入高级指标
                "seal_rate": strategy_info.get("seal_rate", 0),
                "broken_rate": strategy_info.get("broken_rate", 0),
                "next_day_premium": strategy_info.get("next_day_premium", 0),
                "limit_up_days": strategy_info.get("limit_up_days", 0)
            }
            stocks.append(stock_info)
            
    except Exception as e:
        print(f"Error fetching data: {e}")
        
    return stocks

@app.post("/api/watchlist/remove")
async def remove_from_watchlist(request: Request):
    """从自选列表中移除股票"""
    global watchlist_data, watchlist_map, WATCH_LIST
    try:
        data = await request.json()
        code = data.get("code")
        if code and code in watchlist_map:
            # Remove from memory
            del watchlist_map[code]
            watchlist_data = list(watchlist_map.values())
            WATCH_LIST = list(watchlist_map.keys())
            
            # Save to disk
            with open("watchlist.json", "w", encoding="utf-8") as f:
                json.dump(watchlist_data, f, ensure_ascii=False, indent=2)
                
            return {"status": "success", "message": f"Removed {code}"}
        return {"status": "error", "message": "Stock not found"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/stocks")
async def api_stocks():
    return get_stock_quotes()

@app.get("/api/limit_up_pool")
async def api_limit_up_pool():
    return {
        "limit_up": limit_up_pool_data,
        "broken": broken_limit_pool_data
    }

@app.get("/api/intraday_pool")
async def api_intraday_pool():
    """直接获取盘中打板扫描结果"""
    from market_scanner import scan_intraday_limit_up
    loop = asyncio.get_event_loop()
    stocks = await loop.run_in_executor(None, scan_intraday_limit_up)
    return stocks

@app.get("/api/market_sentiment")
async def api_market_sentiment():
    """获取大盘情绪数据"""
    return get_market_overview()

class StockAnalysisRequest(BaseModel):
    code: str
    name: str
    current: float
    change_percent: float
    concept: str = ""
    metrics: dict = {}
    promptType: str = "default"

@app.post("/api/analyze_stock")
async def api_analyze_stock(request: StockAnalysisRequest):
    """
    调用AI分析单个股票
    """
    stock_data = request.dict()
    loop = asyncio.get_event_loop()
    # Pass promptType explicitly or let analyze_single_stock handle it from stock_data
    result = await loop.run_in_executor(None, analyze_single_stock, stock_data)
    return {"status": "success", "analysis": result}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Trigger reload for metrics update
