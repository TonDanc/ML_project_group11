"""Run a concurrent load test against the delivery prediction API."""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_PATH = ROOT / 'tests' / 'cases' / 'good_normal.json'


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return number


def request_prediction(url, body):
    request = Request(
        url,
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=30) as response:
            response.read()  # Include time spent reading the whole response.
            success = 200 <= response.status < 300
    except (URLError, TimeoutError, OSError, ValueError):
        success = False
    return success, (time.perf_counter() - started) * 1000


def percentile(values, percentile_value):
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile_value / 100
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='API base URL, e.g. http://localhost:8000')
    parser.add_argument('--requests', type=positive_int, default=2000, help='number of requests (default: 2000)')
    parser.add_argument('--concurrency', type=positive_int, default=20, help='parallel workers (default: 20)')
    args = parser.parse_args()

    payload = json.loads(PAYLOAD_PATH.read_text(encoding='utf-8'))
    body = json.dumps(payload).encode('utf-8')
    url = args.url.rstrip('/') + '/predict'

    latencies = []
    succeeded = 0
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(request_prediction, url, body)
            for _ in range(args.requests)
        ]
        for future in as_completed(futures):
            success, latency_ms = future.result()
            latencies.append(latency_ms)
            succeeded += int(success)
    duration_s = time.perf_counter() - started

    failed = args.requests - succeeded
    error_rate = failed / args.requests * 100
    throughput = args.requests / duration_s if duration_s else 0.0
    print(f'Successful: {succeeded}')
    print(f'Failed: {failed}')
    print(f'P50: {percentile(latencies, 50):.2f} ms')
    print(f'P95: {percentile(latencies, 95):.2f} ms')
    print(f'Throughput: {throughput:.2f} req/s')
    print(f'Error rate: {error_rate:.2f}%')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
