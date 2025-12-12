from market_scanner import get_market_overview
import json

def debug_overview():
    print("Fetching market overview...")
    try:
        data = get_market_overview(logger=print)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_overview()