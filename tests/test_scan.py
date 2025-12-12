from market_scanner import scan_limit_up_pool, scan_broken_limit_pool, scan_intraday_limit_up

def my_logger(msg):
    print(f"LOG: {msg}")

print("Scanning Limit Up Pool...")
limit_up = scan_limit_up_pool(logger=my_logger)
print(f"Limit Up Count: {len(limit_up)}")
if len(limit_up) > 0:
    print(f"Sample: {limit_up[0]}")

print("\nScanning Broken Limit Pool...")
broken = scan_broken_limit_pool(logger=my_logger)
print(f"Broken Limit Count: {len(broken)}")
if len(broken) > 0:
    print(f"Sample: {broken[0]}")

print("\nScanning Intraday Limit Up Pool...")
intraday = scan_intraday_limit_up(logger=my_logger)
print(f"Intraday Limit Up Count: {len(intraday)}")
if len(intraday) > 0:
    print(f"Sample: {intraday[0]}")
