import requests
import json
import time
from datetime import datetime
import os
import re

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
    
    date_str = datetime.now().strftime('%Y%m%d')
    base_url = "https://push2ex.eastmoney.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    params = {
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "dpt": "wz.ztzt",
        "Pageindex": 0,
        "pagesize": 100, # Top 100
        "sort": "fbt:asc",
        "date": date_str,
        "_": int(time.time() * 1000)
    }

    market_summary = ""
    
    # 1. 涨停池
    try:
        resp = requests.get(base_url + "getTopicZTPool", params=params, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            pool = data.get('data', {}).get('pool', [])
            if pool:
                market_summary += f"【今日涨停池】共 {len(pool)} 家。\n"
                # 提取连板股
                high_board = [s for s in pool if s['lbc'] > 1]
                market_summary += f"连板股 ({len(high_board)}家): " + ", ".join([f"{s['n']}({s['lbc']}板)" for s in high_board]) + "\n"
                # 提取首板代表 (最早涨停)
                first_board = pool[:5]
                market_summary += f"最早涨停: " + ", ".join([f"{s['n']}({s['hybk']})" for s in first_board]) + "\n"
    except Exception as e:
        if logger: logger(f"[!] 获取涨停数据失败: {e}")

    # 2. 炸板池
    try:
        resp = requests.get(base_url + "getTopicZBPool", params=params, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            pool = data.get('data', {}).get('pool', [])
            if pool:
                market_summary += f"【今日炸板池】共 {len(pool)} 家。\n"
                market_summary += f"炸板代表: " + ", ".join([f"{s['n']}" for s in pool[:5]]) + "\n"
    except Exception as e:
        if logger: logger(f"[!] 获取炸板数据失败: {e}")
        
    return market_summary

def get_cls_news(hours=12, logger=None):
    """
    抓取财联社电报最近 N 小时的数据
    """
    msg = f"[*] 正在抓取最近 {hours} 小时的全网舆情 (来源: 财联社)..."
    print(msg)
    if logger: logger(msg)

    current_time = int(time.time())
    start_time = current_time - (hours * 3600)
    
    news_list = []
    last_time = current_time
    
    for page in range(5): 
        params = {
            "rn": 20,
            "last_time": last_time
        }
        
        try:
            resp = requests.get(CLS_API_URL, headers=HEADERS, params=params, timeout=5)
            data = resp.json()
            
            if 'data' not in data or 'roll_data' not in data['data']:
                break
                
            items = data['data']['roll_data']
            if not items:
                break
                
            for item in items:
                item_time = item.get('ctime', 0)
                if item_time < start_time:
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
            
            if logger: logger(f"    已抓取第 {page+1} 页，累计 {len(news_list)} 条...")
            last_time = items[-1].get('ctime')
            time.sleep(1) 
            
        except Exception as e:
            msg = f"[!] Error fetching news: {e}"
            print(msg)
            if logger: logger(msg)
            break
            
    return news_list

def analyze_news_with_deepseek(news_batch, market_summary="", logger=None):
    """
    使用 AI 批量分析新闻和市场数据
    """
    if not news_batch and not market_summary:
        return []

    msg = f"[*] 调用 AI 分析 {len(news_batch)} 条新闻及市场数据..."
    print(msg)
    if logger: logger(msg)

    # 构造 Prompt
    news_content = "\n".join([f"{i+1}. {n['text']}" for i, n in enumerate(news_batch)])
    
    system_prompt = f"""
你是一个A股顶级游资操盘手。你的任务是进行【每日复盘】并挖掘【明日涨停股】。

【今日市场数据】
{market_summary}

【最新舆情新闻】
{news_content}

请结合市场数据（涨停梯队、炸板情况）和新闻舆情，分析市场情绪主线，并预测明日的关注标的。

请严格按照以下标准分类：
1. **Aggressive (竞价抢筹)**: 
   - 核心龙头的一字板预期，或今日强势连板股的弱转强。
   - 策略：开盘集合竞价直接挂单买入。
   
2. **LimitUp (盘中打板)**: 
   - 首板挖掘，或大盘共振的低位补涨股。
   - 策略：放入自选，盘中观察，如果快速拉升或封板则买入。

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

def generate_watchlist(logger=None):
    msg = "[-] 启动复盘分析 (AI Powered)..."
    print(msg)
    if logger: logger(msg)
    
    # 0. 获取市场数据
    market_summary = get_market_data(logger=logger)
    if logger: logger(f"[-] 市场数据获取完成。")

    # 1. 获取新闻
    news_items = get_cls_news(hours=6, logger=logger) # 缩短时间范围，聚焦最新消息
    msg = f"[-] 获取到 {len(news_items)} 条有效资讯。"
    print(msg)
    if logger: logger(msg)
    
    watchlist = {}
    
    # 2. 分批分析 (避免 Token 溢出，每批 10 条)
    batch_size = 10
    # 如果没有新闻，也至少跑一次市场数据分析
    if not news_items:
        news_items = [{"text": "今日无重大新闻，请基于市场数据分析。"}]

    for i in range(0, len(news_items), batch_size):
        batch = news_items[i:i+batch_size]
        # 只有第一批带上完整的 market_summary，避免重复消耗 token
        current_market_summary = market_summary if i == 0 else "（市场数据参考上文）"
        
        analyzed_stocks = analyze_news_with_deepseek(batch, market_summary=current_market_summary, logger=logger)
        
        for stock in analyzed_stocks:
            code = stock['code']
            # 简单的代码格式修正 (确保是 sh/sz 开头)
            if not (code.startswith('sh') or code.startswith('sz')):
                # 尝试修复，比如 600xxx -> sh600xxx
                if code.startswith('6'): code = 'sh' + code
                elif code.startswith('0') or code.startswith('3'): code = 'sz' + code
            
            msg = f"    [+] 挖掘目标: {stock['name']} ({code}) - {stock['strategy']} - {stock['score']}"
            print(msg)
            if logger: logger(msg)
            
            # 去重逻辑：保留分数更高的
            current_score = stock.get('score', 0)
            if code not in watchlist or current_score > watchlist[code]['initial_score']:
                watchlist[code] = {
                    "code": code,
                    "name": stock.get('name', '未知'),
                    "news_summary": stock.get('reason', '无理由'),
                    "concept": stock.get('concept', '其他'),
                    "initial_score": current_score,
                    "strategy_type": stock.get('strategy', 'Neutral') # Aggressive or LimitUp
                }
        
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
            watchlist[t['code']] = {
                "code": t['code'],
                "name": t['name'],
                "news_summary": t['reason'],
                "concept": t['concept'],
                "initial_score": t['score'],
                "strategy_type": t['strategy']
            }

    # 3. 保存结果
    output_file = "watchlist.json"
    final_list = list(watchlist.values())
    final_list.sort(key=lambda x: x['initial_score'], reverse=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
        
    msg = f"[+] 复盘完成。生成 {len(final_list)} 个关注标的 -> {output_file}"
    print(msg)
    if logger: logger(msg)

if __name__ == "__main__":
    generate_watchlist()
