from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, BackgroundTasks, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import requests
import json
import os
import asyncio
import time
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
from app.core.news_analyzer import generate_watchlist, analyze_single_stock
from app.core.market_scanner import scan_limit_up_pool, scan_broken_limit_pool, get_market_overview
from app.core.stock_utils import calculate_metrics
from app.core.data_provider import data_provider
from app.core.time_manager import TimeManager

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TEMPLATE_DIR = BASE_DIR / "app" / "templates"

# Ensure data dir exists
DATA_DIR.mkdir(exist_ok=True)

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

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
    file_path = DATA_DIR / "watchlist.json"
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def reload_watchlist_globals():
    """重新加载全局变量 (复盘后调用)"""
    global watchlist_data, watchlist_map, WATCH_LIST
    watchlist_data = load_watchlist()
    watchlist_map = {item['code']: item for item in watchlist_data}
    WATCH_LIST = list(watchlist_map.keys())

# 全局变量
watchlist_data = load_watchlist()
watchlist_map = {item['code']: item for item in watchlist_data}
WATCH_LIST = list(watchlist_map.keys())
limit_up_pool_data = []
broken_limit_pool_data = []
intraday_pool_data = [] # New global for fast intraday pool
ANALYSIS_CACHE = {} # Cache for AI analysis results: {code: {content: str, timestamp: float}}

def load_analysis_cache():
    """Load AI analysis cache from disk"""
    global ANALYSIS_CACHE
    file_path = DATA_DIR / "analysis_cache.json"
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                ANALYSIS_CACHE = json.load(f)
        except:
            pass

def save_analysis_cache():
    """Save AI analysis cache to disk"""
    try:
        file_path = DATA_DIR / "analysis_cache.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(ANALYSIS_CACHE, f, ensure_ascii=False)
    except:
        pass

def load_market_pools():
    """Load market pools from disk"""
    global limit_up_pool_data, broken_limit_pool_data
    file_path = DATA_DIR / "market_pools.json"
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                limit_up_pool_data = data.get("limit_up", [])
                broken_limit_pool_data = data.get("broken", [])
        except:
            pass

def save_market_pools():
    """Save market pools to disk"""
    try:
        file_path = DATA_DIR / "market_pools.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump({
                "limit_up": limit_up_pool_data,
                "broken": broken_limit_pool_data
            }, f, ensure_ascii=False)
    except:
        pass

# Load caches on startup
load_market_pools()
load_analysis_cache()

async def update_market_pools_task():
    global limit_up_pool_data, broken_limit_pool_data
    loop = asyncio.get_event_loop()
    while True:
        try:
            # Check if we should scan
            if TimeManager.is_trading_day() and TimeManager.is_trading_time():
                # Run blocking IO in executor
                new_limit_up = await loop.run_in_executor(None, scan_limit_up_pool)
                if new_limit_up is not None: # Only update if not None (failed)
                    limit_up_pool_data = new_limit_up
                
                new_broken = await loop.run_in_executor(None, scan_broken_limit_pool)
                if new_broken is not None:
                    broken_limit_pool_data = new_broken
                    
                await loop.run_in_executor(None, save_market_pools)
            else:
                # If not trading time, maybe scan less frequently or just once to ensure data is loaded?
                # For now, just sleep longer
                await asyncio.sleep(60)
                continue

        except Exception as e:
            print(f"Pool update error: {e}")
        
        await asyncio.sleep(10) # Update every 10 seconds

async def update_intraday_pool_task():
    """Fast loop for intraday scanner"""
    global intraday_pool_data, limit_up_pool_data
    from app.core.market_scanner import scan_intraday_limit_up
    loop = asyncio.get_event_loop()
    while True:
        try:
            # Only run during trading hours
            if TimeManager.is_trading_time():
                result = await loop.run_in_executor(None, scan_intraday_limit_up)
                if result:
                    intraday_stocks, sealed_stocks = result
                    intraday_pool_data = intraday_stocks
                    
                    # Merge sealed stocks into limit_up_pool_data if not already present
                    if sealed_stocks:
                        existing_codes = {s['code'] for s in limit_up_pool_data}
                        for s in sealed_stocks:
                            if s['code'] not in existing_codes:
                                limit_up_pool_data.append(s)
                                existing_codes.add(s['code'])
                await asyncio.sleep(10)
            else:
                # Sleep longer when market is closed
                await asyncio.sleep(60)
            
        except Exception as e:
            print(f"Intraday scan error: {e}")
            # Sleep longer on error to avoid hammering
            await asyncio.sleep(60)

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
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: data_provider.search_stock(q))

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
        elif code.startswith('8') or code.startswith('4') or code.startswith('9'):
            code = f"bj{code}"
        else:
            # 默认为 sh (或者报错)
            pass
    
    # 简单的格式校验
    if not (code.startswith('sh') or code.startswith('sz') or code.startswith('bj')):
        return {"status": "error", "message": "Invalid code format"}
        
    # 如果已存在，强制更新为 Manual 策略
    if code in watchlist_map:
        watchlist_map[code]['strategy_type'] = 'Manual'
        watchlist_map[code]['news_summary'] = '手动添加 (覆盖)'
        # Save
        try:
            file_path = DATA_DIR / "watchlist.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(watchlist_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving watchlist: {e}")
        return {"status": "success", "message": "Updated to Manual"}
        
    # 计算高级指标
    metrics = calculate_metrics(code)
    
    # 获取股票详细信息 (名称 + 行业/概念)
    name, concept = data_provider.get_stock_info(code)
    
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
        file_path = DATA_DIR / "watchlist.json"
        with open(file_path, "w", encoding="utf-8") as f:
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

@app.get("/api/market_status")
async def get_market_status():
    return {
        "is_trading_day": TimeManager.is_trading_day(),
        "is_trading_time": TimeManager.is_trading_time(),
        "message": TimeManager.get_market_status_message()
    }

@app.post("/api/watchlist/cleanup")
async def cleanup_watchlist_api():
    """Manually trigger watchlist cleanup"""
    try:
        cleanup_watchlist()
        return {"status": "ok", "message": "Watchlist cleaned up"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def cleanup_watchlist():
    """
    Clean up watchlist: keep only last 50 items or items added within 3 days.
    """
    global watchlist_data, watchlist_map, WATCH_LIST
    file_path = DATA_DIR / "watchlist.json"
    if not file_path.exists():
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Sort by added_time desc
        # If added_time is missing, treat as old (0)
        data.sort(key=lambda x: x.get('added_time', 0), reverse=True)
        
        # Keep top 50
        new_data = data[:50]
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)
            
        # Reload globals
        watchlist_data = new_data
        watchlist_map = {item['code']: item for item in watchlist_data}
        WATCH_LIST = list(watchlist_map.keys())
        
    except Exception as e:
        print(f"Cleanup failed: {e}")

async def update_watchlist_status_task():
    """
    Update watchlist stocks status (check for limit up)
    """
    global watchlist_data
    loop = asyncio.get_event_loop()
    while True:
        try:
            if TimeManager.is_trading_time() and watchlist_data:
                codes = [item['code'] for item in watchlist_data]
                quotes = await loop.run_in_executor(None, data_provider.fetch_quotes, codes)
                
                quote_map = {q['code']: q for q in quotes}
                
                for item in watchlist_data:
                    code = item['code']
                    if code in quote_map:
                        q = quote_map[code]
                        
                        is_20cm = code.startswith('sz30') or code.startswith('sh68')
                        limit_threshold = 19.5 if is_20cm else 9.5
                        
                        item['current_price'] = q['current']
                        item['change_percent'] = q['change_percent']
                        item['is_limit_up'] = q['change_percent'] >= limit_threshold
                        
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Watchlist status update error: {e}")
            await asyncio.sleep(10)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(log_broadcaster())
    # Start background scheduler
    asyncio.create_task(scheduler_loop())
    # Start market pool updater
    asyncio.create_task(update_market_pools_task())
    # Start fast intraday scanner
    asyncio.create_task(update_intraday_pool_task())
    # Start watchlist status updater
    asyncio.create_task(update_watchlist_status_task())
    
    # Initial cleanup
    cleanup_watchlist()
    
    # 启动时立即执行一次盘中扫描，确保列表不为空
    print("Startup: Running initial intraday scan...")
    asyncio.create_task(run_initial_scan())

async def run_initial_scan():
    """启动时立即运行一次扫描"""
    try:
        # 等待几秒确保其他组件就绪
        await asyncio.sleep(2)
        if SYSTEM_CONFIG["auto_analysis_enabled"]:
            await asyncio.to_thread(execute_analysis, "intraday")
            print("Startup: Initial scan completed.")
            # Update last run time to prevent immediate re-run by scheduler
            SYSTEM_CONFIG["last_run_time"] = time.time()
    except Exception as e:
        print(f"Startup scan error: {e}")

# Global Configuration
SYSTEM_CONFIG = {
    "auto_analysis_enabled": True,
    "use_smart_schedule": True,
    "fixed_interval_minutes": 60,
    "last_run_time": 0,
    "next_run_time": 0,
    "current_status": "Idle"
}

def load_config():
    """Load configuration from disk"""
    global SYSTEM_CONFIG
    config_path = DATA_DIR / "config.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                saved_config = json.load(f)
                # Update only persistent fields
                for key in ["auto_analysis_enabled", "use_smart_schedule", "fixed_interval_minutes"]:
                    if key in saved_config:
                        SYSTEM_CONFIG[key] = saved_config[key]
        except Exception as e:
            print(f"Failed to load config: {e}")

def save_config():
    """Save configuration to disk"""
    config_path = DATA_DIR / "config.json"
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({
                "auto_analysis_enabled": SYSTEM_CONFIG["auto_analysis_enabled"],
                "use_smart_schedule": SYSTEM_CONFIG["use_smart_schedule"],
                "fixed_interval_minutes": SYSTEM_CONFIG["fixed_interval_minutes"]
            }, f, indent=2)
    except Exception as e:
        print(f"Failed to save config: {e}")

# Load config on startup
load_config()

@app.get("/api/config")
async def get_config():
    return SYSTEM_CONFIG

class ConfigUpdate(BaseModel):
    auto_analysis_enabled: bool
    use_smart_schedule: bool
    fixed_interval_minutes: int

@app.post("/api/config")
async def update_config(config: ConfigUpdate):
    global SYSTEM_CONFIG
    SYSTEM_CONFIG["auto_analysis_enabled"] = config.auto_analysis_enabled
    SYSTEM_CONFIG["use_smart_schedule"] = config.use_smart_schedule
    SYSTEM_CONFIG["fixed_interval_minutes"] = config.fixed_interval_minutes
    save_config() # Persist changes
    return {"status": "success", "config": SYSTEM_CONFIG}

async def scheduler_loop():
    """Background scheduler for periodic tasks"""
    print("Starting background scheduler...")
    last_pool_update_time = 0
    
    # Startup Check: If watchlist was updated recently (< 1 hour), skip immediate analysis
    # Check file modification time of watchlist.json
    try:
        watchlist_path = DATA_DIR / "watchlist.json"
        if watchlist_path.exists():
            mtime = watchlist_path.stat().st_mtime
            if time.time() - mtime < 3600:
                print("Watchlist updated recently (<1h), skipping immediate analysis on startup.")
                # Set last_run_time to mtime so scheduler thinks it just ran
                SYSTEM_CONFIG["last_run_time"] = mtime
    except Exception as e:
        print(f"Startup check failed: {e}")

    while True:
        current_timestamp = time.time()
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        
        # Weekend Check (Saturday=5, Sunday=6)
        if now.weekday() >= 5:
            # Sleep longer on weekends
            await asyncio.sleep(3600)
            continue

        # --- Schedule Logic ---
        interval_seconds = 3600 # Default 1h
        lookback_hours = 1
        mode = "after_hours"
        
        if SYSTEM_CONFIG["use_smart_schedule"]:
            # 09:30 - 15:00 (Trading) - Intraday Surprise
            if (current_hour > 9 or (current_hour == 9 and current_minute >= 30)) and current_hour < 15:
                interval_seconds = 15 * 60 # 15 mins
                lookback_hours = 0.25
                mode = "intraday"
                
            # 15:00 - 15:15 (Wait)
            elif current_hour == 15 and current_minute < 15:
                interval_seconds = 999999 # Do not run
                
            # 15:15 - 18:00 (Post-market 1h)
            elif current_hour == 15 and current_minute >= 15:
                 interval_seconds = 3600
                 lookback_hours = 1
                 mode = "after_hours"
            elif 16 <= current_hour < 18:
                 interval_seconds = 3600
                 lookback_hours = 1
                 mode = "after_hours"
                 
            # 18:00 - 23:00 (Evening 3h)
            elif 18 <= current_hour < 23:
                 interval_seconds = 3 * 3600
                 lookback_hours = 3
                 mode = "after_hours"
                 
            # 23:00 - 06:00 (Night 6h)
            elif current_hour >= 23 or current_hour < 6:
                 interval_seconds = 6 * 3600
                 lookback_hours = 6
                 mode = "after_hours"
                 
            # 06:00 - 08:30 (Morning 1h)
            elif 6 <= current_hour < 8:
                 interval_seconds = 3600
                 lookback_hours = 1
                 mode = "after_hours"
            elif current_hour == 8 and current_minute < 30:
                 interval_seconds = 3600
                 lookback_hours = 1
                 mode = "after_hours"
                 
            # 08:30 - 09:30 (Pre-open 15m)
            elif current_hour == 8 and current_minute >= 30:
                 interval_seconds = 15 * 60
                 lookback_hours = 0.25
                 mode = "after_hours"
            elif current_hour == 9 and current_minute < 30:
                 interval_seconds = 15 * 60
                 lookback_hours = 0.25
                 mode = "after_hours"

            # Special Trigger: Force run at 15:15 if last run was intraday (before 15:15)
            if current_hour == 15 and current_minute >= 15:
                 last_run_dt = datetime.fromtimestamp(SYSTEM_CONFIG["last_run_time"]) if SYSTEM_CONFIG["last_run_time"] > 0 else datetime.fromtimestamp(0)
                 # If last run was today but before 15:15
                 if last_run_dt.date() == now.date() and (last_run_dt.hour < 15 or (last_run_dt.hour == 15 and last_run_dt.minute < 15)):
                     interval_seconds = 0 # Force run
        else:
            # Manual Interval
            interval_seconds = SYSTEM_CONFIG["fixed_interval_minutes"] * 60
            lookback_hours = SYSTEM_CONFIG["fixed_interval_minutes"] / 60
            # Simple mode logic for manual
            if (current_hour > 9 or (current_hour == 9 and current_minute >= 30)) and current_hour < 15:
                mode = "intraday"
            else:
                mode = "after_hours"

        # Update Next Run Time for UI
        # If we just ran (last_run_time is very close to now), next run is now + interval
        # If we haven't run in a while, next run is effectively "now" (pending execution)
        if SYSTEM_CONFIG["last_run_time"] == 0:
             SYSTEM_CONFIG["next_run_time"] = current_timestamp
        else:
             # Calculate next run based on last run
             next_run = SYSTEM_CONFIG["last_run_time"] + interval_seconds
             # If next run is in the past (overdue), show it as now
             if next_run < current_timestamp:
                 SYSTEM_CONFIG["next_run_time"] = current_timestamp
             else:
                 SYSTEM_CONFIG["next_run_time"] = next_run

        # Task 1: Analysis
        if SYSTEM_CONFIG["auto_analysis_enabled"]:
            if current_timestamp - SYSTEM_CONFIG["last_run_time"] >= interval_seconds:
                # Special check to avoid running during the 15:00-15:15 gap (only in smart mode)
                should_run = True
                if SYSTEM_CONFIG["use_smart_schedule"] and (current_hour == 15 and current_minute < 15):
                    should_run = False
                
                if should_run:
                    try:
                        SYSTEM_CONFIG["current_status"] = f"Running {mode}..."
                        # Update last_run_time BEFORE execution to prevent loop on error
                        SYSTEM_CONFIG["last_run_time"] = current_timestamp
                        
                        # Recalculate next run time immediately after update
                        SYSTEM_CONFIG["next_run_time"] = current_timestamp + interval_seconds
                        
                        thread_logger(f">>> 触发定时分析: {mode}, 周期{interval_seconds/60:.0f}分, 回溯{lookback_hours}小时")
                        await asyncio.to_thread(execute_analysis, mode, lookback_hours)
                    except Exception as e:
                        print(f"Scheduler error: {e}")
                    finally:
                        SYSTEM_CONFIG["current_status"] = "Idle"
        else:
             SYSTEM_CONFIG["current_status"] = "Paused"
        
        # Task 2: Refresh Quotes (Every 3 seconds)
        # Only during trading hours or shortly after
        if now.weekday() < 5 and (9 <= current_hour < 16):
            try:
                stocks = await asyncio.to_thread(get_stock_quotes)
            except Exception as e:
                pass
            
        # Task 3: Update Limit Up Pool (Every 30 seconds)
        if current_timestamp - last_pool_update_time >= 30:
             # Only during trading hours
             if now.weekday() < 5 and (9 <= current_hour < 16):
                 await asyncio.to_thread(update_limit_up_pool_task)
                 last_pool_update_time = current_timestamp

        await asyncio.sleep(5) # Check every 5 seconds

def thread_logger(msg):
    """线程安全的 logger"""
    log_queue.put(msg)

@app.post("/api/analyze")
async def run_analysis(background_tasks: BackgroundTasks, mode: str = Query("after_hours")):
    """触发复盘分析"""
    # 在后台运行，不阻塞 API
    background_tasks.add_task(execute_analysis, mode)
    return {"status": "success", "message": f"{mode} analysis started in background"}

def execute_analysis(mode="after_hours", hours=None):
    try:
        mode_name = "盘后复盘" if mode == "after_hours" else "盘中突击"
        thread_logger(f">>> 开始执行{mode_name}任务 (回溯{hours if hours else '默认'}小时)...")
        generate_watchlist(logger=thread_logger, mode=mode, hours=hours, update_callback=refresh_watchlist)
        refresh_watchlist()
        # Reload globals so /api/stocks returns new data
        reload_watchlist_globals()
        thread_logger(f">>> {mode_name}任务完成，列表已更新 ({len(WATCH_LIST)} 个标的)。")
    except Exception as e:
        thread_logger(f"!!! 分析任务出错: {e}")
        print(f"Analysis Error: {e}")


def get_stock_quotes():
    """
    获取股票行情，使用统一的 DataProvider
    """
    if not WATCH_LIST:
        return []
        
    try:
        # Fetch raw quotes
        raw_stocks = data_provider.fetch_quotes(WATCH_LIST)
        
        # Enrich with strategy info
        enriched_stocks = []
        for stock in raw_stocks:
            code = stock['code']
            strategy_info = watchlist_map.get(code, {})
            
            # Merge strategy info
            stock['strategy'] = strategy_info.get("strategy_type", "Neutral")
            stock['initial_score'] = strategy_info.get("initial_score", 0)
            stock['concept'] = strategy_info.get("concept", "-")
            stock['seal_rate'] = strategy_info.get("seal_rate", 0)
            stock['broken_rate'] = strategy_info.get("broken_rate", 0)
            stock['next_day_premium'] = strategy_info.get("next_day_premium", 0)
            stock['limit_up_days'] = strategy_info.get("limit_up_days", 0)
            
            enriched_stocks.append(stock)
            
        return enriched_stocks
    except Exception as e:
        print(f"Error fetching quotes: {e}")
        return []

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
            file_path = DATA_DIR / "watchlist.json"
            with open(file_path, "w", encoding="utf-8") as f:
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
    """直接获取盘中打板扫描结果 (优先返回缓存)"""
    global intraday_pool_data
    if intraday_pool_data:
        return intraday_pool_data
        
    # Fallback if empty (e.g. startup)
    from app.core.market_scanner import scan_intraday_limit_up
    loop = asyncio.get_event_loop()
    stocks = await loop.run_in_executor(None, scan_intraday_limit_up)
    if stocks:
        intraday_pool_data = stocks
    return stocks

@app.get("/api/market_sentiment")
async def api_market_sentiment():
    """获取大盘情绪数据"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_market_overview)

class StockAnalysisRequest(BaseModel):
    code: str
    name: str
    current: float
    change_percent: float
    concept: str = ""
    metrics: dict = {}
    promptType: str = "default"
    force: bool = False # Force re-analysis
    apiKey: Optional[str] = None # Optional API Key for standalone mode

@app.post("/api/analyze_stock")
async def api_analyze_stock(request: StockAnalysisRequest):
    """
    调用AI分析单个股票 (支持缓存)
    """
    stock_data = request.dict()
    api_key = stock_data.get('apiKey')
    code = stock_data.get('code')
    force = stock_data.get('force', False)
    
    # Check Cache
    if not force and code in ANALYSIS_CACHE:
        cache_entry = ANALYSIS_CACHE[code]
        cache_time = datetime.fromtimestamp(cache_entry['timestamp'])
        now = datetime.now()
        
        # Expiry Logic: Expire at 15:00 daily
        # If cache is from today before 15:00, and now is after 15:00 -> Expired
        # If cache is from yesterday -> Expired
        is_expired = False
        if cache_time.date() < now.date():
            is_expired = True
        elif cache_time.hour < 15 and now.hour >= 15:
            is_expired = True
            
        if not is_expired:
            return {"status": "success", "analysis": cache_entry['content'], "cached": True}

    loop = asyncio.get_event_loop()
    # Pass promptType explicitly or let analyze_single_stock handle it from stock_data
    # Pass api_key if provided
    result = await loop.run_in_executor(None, lambda: analyze_single_stock(stock_data, prompt_type=request.promptType, api_key=api_key))
    
    # Update Cache
    if result and not result.startswith("分析失败"):
        ANALYSIS_CACHE[code] = {
            "content": result,
            "timestamp": time.time()
        }
        # Persist cache to disk
        save_analysis_cache()
        
    return {"status": "success", "analysis": result, "cached": False}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Trigger reload for metrics update
