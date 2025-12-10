from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, BackgroundTasks, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import requests
import json
import os
import asyncio
from typing import List
from news_analyzer import generate_watchlist

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

@app.post("/api/add_stock")
async def add_stock(code: str):
    """手动添加股票到监控列表"""
    global watchlist_data, watchlist_map, WATCH_LIST
    
    # 简单的格式校验
    if not (code.startswith('sh') or code.startswith('sz')):
        return {"status": "error", "message": "Invalid code format"}
        
    # 如果已存在，忽略
    if code in watchlist_map:
        return {"status": "success", "message": "Already exists"}
        
    # 添加新股票
    new_item = {
        "code": code,
        "name": "手动添加", # 名字会在下次抓取时更新
        "news_summary": "Manual Add",
        "concept": "自选",
        "initial_score": 5, # 默认中等分数
        "strategy_type": "Manual"
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

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(log_broadcaster())

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


def get_sina_data():
    """
    从新浪财经接口抓取数据并清洗
    """
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
                "concept": strategy_info.get("concept", "-")
            }
            stocks.append(stock_info)
            
    except Exception as e:
        print(f"Error fetching data: {e}")
        
    return stocks

@app.get("/api/stocks")
async def api_stocks():
    return get_sina_data()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
