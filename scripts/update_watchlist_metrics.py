import json
from stock_utils import calculate_metrics
import time

def update_watchlist():
    try:
        with open('watchlist.json', 'r', encoding='utf-8') as f:
            watchlist = json.load(f)
    except FileNotFoundError:
        print("watchlist.json not found.")
        return

    updated_count = 0
    for stock in watchlist:
        code = stock['code']
        print(f"Updating metrics for {code}...")
        
        # Calculate metrics
        metrics = calculate_metrics(code)
        
        # Update stock object
        stock['seal_rate'] = metrics['seal_rate']
        stock['broken_rate'] = metrics['broken_rate']
        stock['next_day_premium'] = metrics['next_day_premium']
        stock['limit_up_days'] = metrics['limit_up_days']
        
        updated_count += 1
        time.sleep(0.5) # Be nice to the API

    with open('watchlist.json', 'w', encoding='utf-8') as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=2)
        
    print(f"Updated {updated_count} stocks in watchlist.json")

if __name__ == "__main__":
    update_watchlist()
