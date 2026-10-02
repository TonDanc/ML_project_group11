"""Validate order case JSON files locally or against a running API."""

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
import pandera.errors as pe

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = Path(__file__).resolve().parent / 'cases'
sys.path.insert(0, str(ROOT / 'src'))

from schema import input_schema


def check_local(payload, expects_valid):
	try:
		input_schema.validate(pd.DataFrame([payload]))
	except (pe.SchemaError, pe.SchemaErrors) as error:
		detail = ' '.join(str(error).split())
		if expects_valid:
			return False, f'schema rejected valid case ({type(error).__name__}): {detail}'
		return True, f'rejected as expected ({type(error).__name__}): {detail}'

	if not expects_valid:
		return False, 'schema accepted invalid case'
	return True, 'schema accepted payload as expected'


def check_url(payload, expects_valid, base_url):
	request = Request(
		base_url.rstrip('/') + '/predict',
		data=json.dumps(payload).encode('utf-8'),
		headers={'Content-Type': 'application/json'},
		method='POST',
	)
	try:
		with urlopen(request, timeout=10) as response:
			status = response.status
	except HTTPError as error:
		status = error.code
	except URLError as error:
		return False, f'could not reach API: {error.reason}'

	expected_status = 200 if expects_valid else 422
	if status != expected_status:
		return False, f'HTTP {status}; expected {expected_status}'
	return True, f'HTTP {status} as expected'


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('--url', help='test a running API, e.g. http://localhost:8000')
	args = parser.parse_args()

	case_files = sorted(CASES_DIR.glob('*.json'))
	if not case_files:
		print(f'FAIL: no JSON case files found in {CASES_DIR}')
		return 1

	failures = 0
	for case_file in case_files:
		expects_valid = case_file.name.startswith('good_')
		if not expects_valid and not case_file.name.startswith('bad_'):
			print(f'FAIL {case_file.name}: filename must start with good_ or bad_')
			failures += 1
			continue

		try:
			payload = json.loads(case_file.read_text(encoding='utf-8'))
			if not isinstance(payload, dict):
				raise ValueError('payload must be a JSON object')
			if args.url:
				passed, detail = check_url(payload, expects_valid, args.url)
			else:
				passed, detail = check_local(payload, expects_valid)
		except Exception as error:
			passed, detail = False, f'{type(error).__name__}: {error}'

		if passed:
			print(f'PASS {case_file.name}: {detail}')
		else:
			print(f'FAIL {case_file.name}: {detail}')
			failures += 1

	if failures:
		print(f'{failures} of {len(case_files)} case file(s) failed.')
		return 1

	print(f'All {len(case_files)} case files passed.')
	return 0


if __name__ == '__main__':
	raise SystemExit(main())
