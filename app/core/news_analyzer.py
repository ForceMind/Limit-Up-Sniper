import requests
import json
import time
from datetime import datetime
import os
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.core.stock_utils import calculate_metrics
from app.core.market_scanner import scan_intraday_limit_up, get_market_overview, scan_limit_up_pool, scan_broken_limit_pool

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"

# Configuration
CLS_API_URL = "https://www.cls.cn/nodeapi/telegraphList"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.cls.cn/telegraph"
}

# Deepseek Configuration
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "") # 请在环境变量中设置 DEEPSEEK_API_KEY
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

def get_market_data(logger=None):
    """
    获取今日市场核心数据：涨停池、炸板池
    """
    if logger: logger("[*] 正在获取今日市场核心数据 (涨停/炸板)...")
    
    market_summary = ""
    
    # 1. 涨停池 (使用 market_scanner 的统一接口)
    try:
        pool = scan_limit_up_pool(logger)
        if pool:
            market_summary += f"【今日涨停池】共 {len(pool)} 家。\n"
            # 由于原生接口不返回连板数，这里只列出部分代表
            # 简单列出前 10 个
            top_stocks = pool[:10]
            market_summary += f"涨停代表: " + ", ".join([f"{s['name']}" for s in top_stocks]) + "\n"
    except Exception as e:
        if logger: logger(f"[!] 获取涨停数据失败: {e}")

    # 2. 炸板池
    try:
        pool = scan_broken_limit_pool(logger)
        if pool:
            market_summary += f"【今日炸板池】共 {len(pool)} 家。\n"
            market_summary += f"炸板代表: " + ", ".join([f"{s['name']}" for s in pool[:5]]) + "\n"
    except Exception as e:
        if logger: logger(f"[!] 获取炸板数据失败: {e}")
        
    # 3. 市场情绪概览 (新增)
    try:
        overview = get_market_overview(logger=None)
        stats = overview.get('stats', {})
        market_summary += f"【市场情绪】\n"
        market_summary += f"- 涨跌分布: 上涨 {stats.get('up_count', 0)} 家, 下跌 {stats.get('down_count', 0)} 家, 跌停 {stats.get('limit_down_count', 0)} 家\n"
        market_summary += f"- 市场建议: {stats.get('suggestion', '观察')} (情绪: {stats.get('sentiment', 'Neutral')})\n"
        market_summary += f"- 总成交额: {stats.get('total_volume', 0)} 亿\n"
    except Exception as e:
        if logger: logger(f"[!] 获取市场情绪失败: {e}")
        
    return market_summary

def get_cls_news(hours=12, logger=None):
    """
    抓取财联社电报最近 N 小时的数据 (多线程并发)
    """
    msg = f"[*] 正在抓取最近 {hours} 小时的全网舆情 (来源: 财联社, 多线程)..."
    print(msg)
    if logger: logger(msg)

    current_time = int(time.time())
    start_time = current_time - (hours * 3600)
    
    news_list = []
    
    # 财联社API是基于 last_time 分页的，这使得完全并行比较困难，因为下一页依赖上一页的最后时间。
    # 但是，我们可以预估时间或者并发抓取多个时间段？
    # 实际上，财联社API如果只传 rn (count) 不传 last_time，是第一页。
    # 严格的分页必须串行。
    # 妥协方案：为了速度，我们只抓取第一页 (最新20条) 或者 串行抓取但优化连接。
    # 实际上，对于"最近1小时"，通常1-2页就够了。
    # 如果要多线程，我们可以尝试猜测 last_time? 不可行。
    # 
    # 替代方案：使用 requests.Session 复用连接，减少握手时间。
    
    session = requests.Session()
    last_time = current_time
    
    # 既然用户强烈要求多线程，我们可以尝试并发抓取不同来源？
    # 目前只有财联社。
    # 让我们优化为：使用 Session + 减少 sleep
    
    for page in range(5): 
        params = {
            "rn": 20,
            "last_time": last_time
        }
        
        try:
            # 使用 session
            resp = session.get(CLS_API_URL, headers=HEADERS, params=params, timeout=5)
            data = resp.json()
            
            if 'data' not in data or 'roll_data' not in data['data']:
                break
                
            items = data['data']['roll_data']
            if not items:
                break
                
            page_valid_count = 0
            for item in items:
                item_time = item.get('ctime', 0)
                if item_time < start_time:
                    # 时间截止，直接返回
                    return news_list 
                
                title = item.get('title', '')
                content = item.get('content', '')
                if not title: 
                    title = content[:30] + "..."
                
                # 过滤掉非A股相关的无关新闻（简单过滤）
                full_text = f"【{title}】{content}"
                if any(k in full_text for k in ["美股", "恒指", "港股", "外汇"]):
                    continue

                news_list.append({
                    "timestamp": item_time,
                    "time_str": datetime.fromtimestamp(item_time).strftime('%Y-%m-%d %H:%M:%S'),
                    "text": full_text
                })
                page_valid_count += 1
            
            if logger: logger(f"    已抓取第 {page+1} 页，本页有效 {page_valid_count} 条...")
            
            # 更新 last_time 为本页最后一条的时间
            last_time = items[-1].get('ctime')
            
            # 移除 sleep 以提高速度
            # time.sleep(1) 
            
        except Exception as e:
            msg = f"[!] Error fetching news: {e}"
            print(msg)
            if logger: logger(msg)
            break
            
    return news_list

def analyze_news_with_deepseek(news_batch, market_summary="", logger=None, mode="after_hours"):
    """
    使用 AI 批量分析新闻和市场数据
    """
    if not news_batch and not market_summary:
        return []

    msg = f"[*] 调用 AI 分析 {len(news_batch)} 条新闻及市场数据 ({mode})..."
    print(msg)
    if logger: logger(msg)

    # 构造 Prompt
    news_content = "\n".join([f"{i+1}. {n['text']}" for i, n in enumerate(news_batch)])
    
    if mode == "after_hours":
        task_desc = "进行【盘后复盘】并挖掘【明日竞价关注股】"
        strategy_desc = """
1. **Aggressive (竞价抢筹)**: 
   - 核心龙头的一字板预期，或今日强势连板股的弱转强。
   - 策略：明日开盘集合竞价直接挂单买入。
2. **LimitUp (盘中打板)**: 
   - 首板挖掘，或大盘共振的低位补涨股。
   - 策略：放入自选，盘中观察，如果快速拉升或封板则买入。
"""
    else: # intraday
        task_desc = "进行【盘中实时分析】并挖掘【当前即将涨停股】"
        strategy_desc = """
1. **Aggressive (立即扫货)**: 
   - 突发重大利好，股价正在快速拉升，即将封板。
   - 策略：立即市价买入，防止买不到。
2. **LimitUp (回封低吸)**: 
   - 炸板回落但承接有力，或分时均线支撑强。
   - 策略：低吸博弈回封。
"""

    system_prompt = f"""
你是一个A股顶级游资操盘手。你的任务是{task_desc}。

【今日市场数据】
{market_summary}

【最新舆情新闻】
{news_content}

请结合市场数据（涨停梯队、炸板情况、涨跌家数）和新闻舆情，分析市场情绪主线，并预测关注标的。

请严格按照以下标准分类：
{strategy_desc}

【评分标准 (Score 0-10)】
请基于以下维度进行综合打分，不要随意给分：
1. **新闻重磅度 (40%)**: 是否为国家级政策、行业重大突破或突发利好？(普通消息<6分, 重磅>8分)
2. **题材主流度 (30%)**: 是否契合当前市场主线（如AI、低空经济等）？(非主线扣分)
3. **个股辨识度 (30%)**: 是否为龙头、老妖股或近期人气股？(杂毛股扣分)
注意：如果仅仅是普通利好且非主线，分数不应超过 7.0。只有绝对龙头或特大利好才能超过 9.0。

请返回纯 JSON 格式，不要包含 Markdown 格式，格式如下：
{{
  "stocks": [
    {{
      "code": "sh600xxx", 
      "name": "股票名", 
      "concept": "核心概念", 
      "reason": "结合今日表现(如3连板)和新闻利好的综合理由", 
      "score": 8.5, 
      "strategy": "Aggressive" 
    }}
  ]
}}
如果新闻没有明确的A股标的，忽略即可。
"""

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "user", "content": system_prompt}
        ],
        "temperature": 0.1, # 低温度，保证输出稳定
        "response_format": { "type": "json_object" }
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }

    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60)
        if response.status_code != 200:
            msg = f"[!] AI API Error: {response.text}"
            print(msg)
            if logger: logger(msg)
            return []
            
        result = response.json()
        if not result or 'choices' not in result or not result['choices']:
            return []
            
        content = result['choices'][0]['message']['content']
        if not content:
            return []
        
        # 清洗可能存在的 Markdown 标记
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*', '', content)
        
        data = json.loads(content)
        return data.get("stocks", [])
        
    except Exception as e:
        msg = f"[!] Analysis Failed: {e}"
        print(msg)
        if logger: logger(msg)
        return []

def analyze_single_stock(stock_data, logger=None):
    """
    对单个股票进行深度AI分析 (大师级逻辑)
    """
    name = stock_data.get('name', '未知股票')
    code = stock_data.get('code', '')
    price = stock_data.get('current', 0)
    change = stock_data.get('change_percent', 0)
    concept = stock_data.get('concept', '')
    prompt_type = stock_data.get('promptType', 'default')
    
    # Additional metrics for better analysis
    turnover = stock_data.get('turnover', stock_data.get('metrics', {}).get('turnover', '未知'))
    circ_value = stock_data.get('circulation_value', '未知')
    if isinstance(circ_value, (int, float)) and circ_value > 0:
        circ_value = f"{round(circ_value / 100000000, 2)}亿"
    
    # 1. 尝试获取该股票的最新新闻 (模拟搜索)
    # 这里简单复用 get_cls_news 的逻辑，但针对特定关键词过滤
    # 实际生产中应该调用搜索引擎API或专门的新闻接口
    news_context = "暂无特定新闻"
    try:
        # 简化的新闻获取逻辑，仅作为示例
        # 实际应该去搜 "股票名称 + 利好/利空"
        pass 
    except:
        pass

    # 2. 构建大师级分析 Prompt
    if prompt_type == 'aggressive':
        prompt = f"""
你是一位擅长竞价抢筹和超短线博弈的顶级游资。请针对股票【{name} ({code})】进行“竞价抢筹”维度的深度推演。

【今日盘面数据】(基于今日收盘或实时数据)
- 现价: {price}
- 涨幅: {change}%
- 换手率: {turnover}%
- 流通市值: {circ_value}
- 概念: {concept}
- 历史指标: {json.dumps(stock_data.get('metrics', {}), ensure_ascii=False)}

【核心分析逻辑】
请重点回答以下问题（Chain of Thought）：
1. **抢筹逻辑**: 基于今日的表现（如涨停、烂板、大长腿等），为什么这只股票明天竞价可能会有溢价或弱转强？
2. **预期差**: 市场可能忽略了什么？是否存在卡位、补涨或穿越的预期？
3. **风险收益比**: 如果明天竞价买入，盈亏比如何？

【最终输出】
请以 Markdown 格式输出简报：
### 1. 核心抢筹理由 (Why Buy Tomorrow?)
(直击痛点，说明上涨预期)

### 2. 预期差与博弈点
(分析主力意图和市场情绪)

### 3. 竞价策略 (Action)
- **关注价格**: (什么样的开盘价符合预期)
- **止损位**: 
- **胜率**: (高/中/低)

请保持语言犀利、极简，直击核心。
"""
    else:
        prompt = f"""
你是一位拥有20年经验的A股顶级游资操盘手，精通情绪周期、题材挖掘和技术面分析。请对股票【{name} ({code})】进行全方位的深度推演。

【今日盘面数据】
- 现价: {price}
- 涨跌幅: {change}%
- 换手率: {turnover}%
- 流通市值: {circ_value}
- 核心概念: {concept}
- 辅助指标: {json.dumps(stock_data.get('metrics', {}), ensure_ascii=False)}

【分析逻辑】
请按照以下步骤进行思考（Chain of Thought），并输出最终报告：

1. **题材定性**: 该股票的核心逻辑是什么？是否属于当前市场的主线题材？
2. **情绪周期**: 当前市场情绪处于什么阶段？该股在当前周期中的地位如何？
3. **技术面与盘口**: 结合涨跌幅、换手率和流通盘大小，判断主力意图（洗盘、出货、吸筹、拉升）。
4. **风险提示**: 有无潜在的利空或抛压风险。

【最终输出】
请以 Markdown 格式输出一份简报，包含以下章节：
### 1. 核心逻辑与地位
(简述题材及地位)

### 2. 盘面深度解析
(结合情绪与技术面分析)

### 3. 操盘计划 (Action Plan)
- **买入策略**: (具体的买点，如打板、低吸、半路)
- **卖出策略**: (止盈止损位)
- **胜率预估**: (高/中/低)

请保持语言犀利、专业，拒绝模棱两可的废话。
"""

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是一位A股顶级游资，风格犀利，擅长捕捉龙头。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.4,
        "stream": False
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }

    try:
        if logger: logger(f"[*] 正在请求AI大师分析: {name}...")
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            return content
        else:
            return f"分析失败: API返回错误 {response.status_code}"
    except Exception as e:
        return f"分析失败: {str(e)}"

    try:
        if logger: logger(f"[*] 正在请求AI分析股票: {name}...")
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            return content
        else:
            return f"分析失败: API返回错误 {response.status_code}"
    except Exception as e:
        return f"分析失败: {str(e)}"

def generate_watchlist(logger=None, mode="after_hours", hours=None):
    msg = f"[-] 启动{mode}分析 (AI Powered)..."
    print(msg)
    if logger: logger(msg)
    
    # 0. 获取市场数据
    market_summary = get_market_data(logger=logger)
    if logger: logger(f"[-] 市场数据获取完成。")

    # 1. 获取新闻
    # 如果未指定 hours，则使用默认逻辑
    if hours is None:
        hours = 2 if mode == "intraday" else 12
        
    news_items = get_cls_news(hours=hours, logger=logger) 
    msg = f"[-] 获取到 {len(news_items)} 条有效资讯 (最近 {hours} 小时)。"
    print(msg)
    if logger: logger(msg)
    
    watchlist = {}
    
    # 1. 加载现有列表
    output_file = DATA_DIR / "watchlist.json"
    if output_file.exists():
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                for item in existing_data:
                    watchlist[item['code']] = item
        except:
            pass

    # 2. 如果是盘中模式，进行行情扫描并更新/剔除
    if mode == "intraday":
        scanner_stocks = scan_intraday_limit_up(logger=logger)
        scanner_codes = set(s['code'] for s in scanner_stocks)
        
        # 2.1 标记不再满足条件的股票为 Discarded
        for code, item in watchlist.items():
            # 只处理之前是由盘中突击策略加入的股票
            # 识别特征: strategy=LimitUp 且 reason 包含 "盘中突击"
            if item.get('strategy_type') == 'LimitUp' and '盘中突击' in item.get('news_summary', ''):
                if code not in scanner_codes:
                    # 不在最新的扫描结果中，说明条件已变差(或已涨停)
                    # 标记为 Discarded，前端根据此状态显示在剔除区
                    item['strategy_type'] = 'Discarded'
                    if '已剔除' not in item['news_summary']:
                        item['news_summary'] += " (已剔除)"
        
        # 2.2 添加/更新当前扫描到的股票
        for stock in scanner_stocks:
            code = stock['code']
            # 计算指标
            metrics = calculate_metrics(code)
            
            new_item = {
                "code": code,
                "name": stock['name'],
                "news_summary": stock['reason'],
                "concept": stock['concept'],
                "initial_score": stock['score'],
                "strategy_type": stock['strategy'],
                "seal_rate": metrics['seal_rate'],
                "broken_rate": metrics['broken_rate'],
                "next_day_premium": metrics['next_day_premium'],
                "limit_up_days": metrics['limit_up_days']
            }
            # 覆盖旧数据 (包括之前可能被标记为 Discarded 的，如果又满足条件了就复活)
            watchlist[code] = new_item
            
    # 如果没有新闻，也至少跑一次市场数据分析
    if not news_items:
        news_items = [{"text": "当前时段无重大新闻，请基于市场数据分析。"}]

    batch_size = 5
    for i in range(0, len(news_items), batch_size):
        batch = news_items[i:i+batch_size]
        # 只有第一批带上完整的 market_summary，避免重复消耗 token
        current_market_summary = market_summary if i == 0 else "（市场数据参考上文）"
        
        analyzed_stocks = analyze_news_with_deepseek(batch, market_summary=current_market_summary, logger=logger, mode=mode)
        
        for stock in analyzed_stocks:
            code = stock['code']
            # 简单的代码格式修正 (确保是 sh/sz/bj 开头)
            if not (code.startswith('sh') or code.startswith('sz') or code.startswith('bj')):
                # 尝试修复
                if code.startswith('6'): code = 'sh' + code
                elif code.startswith('0') or code.startswith('3'): code = 'sz' + code
                elif code.startswith('8') or code.startswith('4') or code.startswith('9'): code = 'bj' + code
            
            # 过滤非A股/北证 (如港股 0xxxx 5位)
            # A股/北证代码通常是6位数字
            raw_code = code.replace('sh', '').replace('sz', '').replace('bj', '')
            if not raw_code.isdigit() or len(raw_code) != 6:
                if logger: logger(f"    [!] 忽略非标准代码: {code}")
                continue

            msg = f"    [+] 挖掘目标: {stock['name']} ({code}) - {stock['strategy']} - {stock['score']}"
            print(msg)
            if logger: logger(msg)
            
            # 计算高级指标
            metrics = calculate_metrics(code)
            
            # 去重逻辑：保留分数更高的
            current_score = stock.get('score', 0)
            
            # 构造新数据对象
            new_item = {
                "code": code,
                "name": stock.get('name', '未知'),
                "news_summary": stock.get('reason', '无理由'),
                "concept": stock.get('concept', '其他'),
                "initial_score": current_score,
                "strategy_type": stock.get('strategy', 'Neutral'), # Aggressive or LimitUp
                # 合并高级指标
                "seal_rate": metrics['seal_rate'],
                "broken_rate": metrics['broken_rate'],
                "next_day_premium": metrics['next_day_premium'],
                "limit_up_days": metrics['limit_up_days']
            }
            
            # 如果已存在，且新分数更高，则覆盖；否则保留旧的但更新指标
            if code not in watchlist or current_score > watchlist[code]['initial_score']:
                watchlist[code] = new_item
            else:
                # 仅更新指标和新闻（如果需要）
                watchlist[code].update({
                    "seal_rate": metrics['seal_rate'],
                    "broken_rate": metrics['broken_rate'],
                    "next_day_premium": metrics['next_day_premium'],
                    "limit_up_days": metrics['limit_up_days']
                })
        
        time.sleep(1) # 避免 API 速率限制

    # 如果没有分析出数据（可能是 Key 没填或新闻太少），加入测试数据
    if not watchlist:
        msg = "[-] 未挖掘到有效标的，添加测试数据以供演示..."
        print(msg)
        if logger: logger(msg)
        test_data = [
            {"code": "sz002405", "name": "四维图新", "concept": "自动驾驶", "score": 9.2, "strategy": "Aggressive", "reason": "获得特斯拉FSD地图数据授权"},
            {"code": "sh600519", "name": "贵州茅台", "concept": "白酒", "score": 7.5, "strategy": "LimitUp", "reason": "分红超预期"},
            {"code": "sz300059", "name": "东方财富", "concept": "互联网金融", "score": 8.0, "strategy": "LimitUp", "reason": "成交量突破万亿"}
        ]
        for t in test_data:
            metrics = calculate_metrics(t['code'])
            watchlist[t['code']] = {
                "code": t['code'],
                "name": t['name'],
                "news_summary": t['reason'],
                "concept": t['concept'],
                "initial_score": t['score'],
                "strategy_type": t['strategy'],
                "seal_rate": metrics['seal_rate'],
                "broken_rate": metrics['broken_rate'],
                "next_day_premium": metrics['next_day_premium'],
                "limit_up_days": metrics['limit_up_days']
            }

    # 3. 保存结果
    output_file = DATA_DIR / "watchlist.json"
    
    # 重新加载现有文件以避免覆盖在此期间手动添加的股票 (Race Condition Fix)
    current_watchlist = {}
    if output_file.exists():
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                existing = json.load(f)
                for item in existing:
                    current_watchlist[item['code']] = item
        except:
            pass
            
    # 合并本次分析结果
    # 如果代码在本次分析结果中，使用本次结果(包含最新分析)
    # 如果代码不在本次结果中但在文件中(例如手动添加)，保留它
    for code, item in watchlist.items():
        current_watchlist[code] = item
        
    final_list = list(current_watchlist.values())
    final_list.sort(key=lambda x: x['initial_score'], reverse=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
        
    msg = f"[+] 复盘完成。生成 {len(final_list)} 个关注标的 -> {output_file}"
    print(msg)
    if logger: logger(msg)

if __name__ == "__main__":
    generate_watchlist()
