import json
from app.core.data_provider import data_provider

def fetch_history_data(code, days=300):
    """
    Fetch last N days of K-line data.
    """
    return data_provider.fetch_history_data(code, days)

def calculate_metrics(code):
    """
    Calculate advanced metrics based on history.
    """
    klines = fetch_history_data(code, days=300)
    if not klines:
        return {
            "seal_rate": 0,
            "broken_rate": 0,
            "next_day_premium": 0,
            "limit_up_days": 0
        }
    
    # Parse data
    # Sina Format: [{"day":"2023-01-01","open":"10.0","high":"10.5","low":"9.9","close":"10.2","volume":"1000"}, ...]
    
    parsed_data = []
    for item in klines:
        parsed_data.append({
            "date": item['day'],
            "open": float(item['open']),
            "close": float(item['close']),
            "high": float(item['high']),
            "low": float(item['low'])
        })
        
    # Determine limit up threshold
    # 20% for 688(sh) and 300(sz), 30% for 8xx(bj - ignored for now), 10% others
    is_20cm = code.startswith('sh688') or code.startswith('sz30')
    limit_threshold = 1.195 if is_20cm else 1.095
    
    first_board_attempts = 0
    first_board_failures = 0
    
    consecutive_attempts = 0
    consecutive_successes = 0
    
    premium_sum = 0
    premium_count = 0
    
    # Calculate metrics
    for i in range(1, len(parsed_data)):
        prev = parsed_data[i-1]
        curr = parsed_data[i]
        
        prev_close = prev['close']
        
        # Check if touched limit up (High >= Limit Price approx)
        high_pct = curr['high'] / prev_close
        is_attempt = high_pct >= limit_threshold
        is_sealed = (curr['close'] / prev_close) >= limit_threshold
        
        # Check if previous day was limit up
        prev_is_limit_up = False
        if i > 1:
            prev_prev = parsed_data[i-2]
            if (prev['close'] / prev_prev['close']) >= limit_threshold:
                prev_is_limit_up = True
        
        if is_attempt:
            if prev_is_limit_up:
                # Consecutive attempt (Promotion)
                consecutive_attempts += 1
                if is_sealed:
                    consecutive_successes += 1
            else:
                # First board attempt
                first_board_attempts += 1
                if not is_sealed:
                    first_board_failures += 1
            
            if is_sealed:
                # Calculate next day premium if available
                if i + 1 < len(parsed_data):
                    next_day = parsed_data[i+1]
                    # Premium = (Open - PrevClose) / PrevClose
                    premium = ((next_day['open'] - curr['close']) / curr['close']) * 100
                    premium_sum += premium
                    premium_count += 1

    # Finalize metrics
    seal_rate = 0
    if first_board_attempts > 0:
        seal_rate = ((first_board_attempts - first_board_failures) / first_board_attempts) * 100
        
    broken_rate = 0
    if first_board_attempts > 0:
        broken_rate = (first_board_failures / first_board_attempts) * 100
        
    next_day_premium = 0
    if premium_count > 0:
        next_day_premium = premium_sum / premium_count
        
    # Calculate current limit up days (consecutive)
    limit_up_days = 0
    for i in range(len(parsed_data)-1, 0, -1):
        curr = parsed_data[i]
        prev = parsed_data[i-1]
        if (curr['close'] / prev['close']) >= limit_threshold:
            limit_up_days += 1
        else:
            break
            
    return {
        "seal_rate": round(seal_rate, 1),
        "broken_rate": round(broken_rate, 1),
        "next_day_premium": round(next_day_premium, 2),
        "limit_up_days": limit_up_days
    }
