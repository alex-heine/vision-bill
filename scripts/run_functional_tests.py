# Functional Test Runner (Example)
import json

import requests


def run_functional_test(endpoint, data_file):
    """Runs a structured test against a service endpoint."""
    try:
        with open(data_file, 'r') as f:
            payload = json.load(f)
    except FileNotFoundError:
        print(f"Error: Data file {data_file} not found.")
        return

    # Assuming the test data provides endpoints and payloads
    endpoint_url = payload.get("endpoint")
    test_payload = payload.get("data")
    expected_status = payload.get("expected_status")

    if not endpoint_url or not test_payload:
        print("Missing endpoint or data in test payload.")
        return

    try:
        response = requests.post(endpoint_url, json=test_payload)
    except requests.exceptions.ConnectionError as e:
        print(f"Connection error to {endpoint_url}: {e}")
        return

    if response.status_code == expected_status:
        print("✅ Success!")
    else:
        print(f"❌ Failure! Expected status code: {expected_status}, Got: {response.status_code}")

if __name__ == "__main__":
    # Placeholder: Iterate over all test data files in tests/data
    pass