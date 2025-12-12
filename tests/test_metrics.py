from stock_utils import calculate_metrics

codes = ['sh600519', 'sz300603']

for code in codes:
    print(f"Testing {code}...")
    metrics = calculate_metrics(code)
    print(f"Metrics: {metrics}")
    print("-" * 20)

