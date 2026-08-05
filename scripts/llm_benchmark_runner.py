# script_batch_comparison.py
import time
from abc import ABC, abstractmethod


# --- Abstract Base Class (The Contract) ---
class BaseServiceInterface(ABC):
    """Defines the generic interface for any LLM service provider."""

    @abstractmethod
    def analyze_receipt(self, image_path: str) -> dict:
        """Processes an image and returns a structured analysis of the content."""

# --- Mock Implementations (for testing structure) ---
class MockLLMAnalyzer(BaseServiceInterface):
    """A mock implementation for demonstration purposes."""
    def __init__(self, name: str):
        self.name = name

    def analyze_receipt(self, image_path: str) -> dict:
        # Simulates LLM call and returns a dictionary payload
        print(f"  -> Calling {self.name} for {image_path}...")
        time.sleep(0.1) # Simulate network latency
        return {"field_a": "mock_value", "field_b": "mock_value"}

def get_model_interface(model_name: str) -> BaseServiceInterface:
    """Factory function to get the correct model interface."""
    if model_name == "llama3":
         return MockLLMAnalyzer("Llama3")
    elif model_name == "phi3":
        return MockLLMAnalyzer("Phi3")
    else:
        raise ValueError(f"Unsupported model: {model_name}")

# --- Helper Functions ---
def get_all_image_paths(data_dir: str) -> list[str]:
    """Glob search imitation: Finds all placeholder image paths."""
    print(f"Scanning directory: {data_dir}...")
    # Mocking 3 file paths for demonstration
    return [
        f"{data_dir}/01_receipt.jpg",
        f"{data_dir}/02_invoice.jpg",
        f"{data_dir}/03_coupon.jpg"
    ]

def load_ground_truth(file_path: str) -> dict:
    """Loads the expected JSON ground truth for validation."""
    # In a real scenario, this would use json.load() on sibling *.json file
    return {"field_a": "expected_A", "field_b": "expected_B"}

def calculate_field_accuracy(analysis: dict, ground_truth: dict) -> float:
    """Calculates the field hit rate (e.g., count of matching fields / total fields)."""
    # Basic mock calculation based on keys present
    num_matches = sum(1 for k in analysis if k in ground_truth and str(analysis[k]) == str(ground_truth[k]))
    return num_matches / max(1, len(analysis))

def measure_execution_time() -> float:
    """Measures the total time taken per receipt processing."""
    return 0.5 # Mocked latency measurement

# --- Core Logic ---

def run_single_receipt_test(service: BaseServiceInterface, image_path: str, expected_json: dict) -> tuple[dict, dict]:
    """Runs one single test for a receipt using the provided service interface."""
    analysis = service.analyze_receipt(image_path)
    hit_rate = calculate_field_accuracy(analysis, expected_json)
    latency = measure_execution_time()
    return analysis, hit_rate


def run_full_llm_benchmark(data_dir: str = "${{workspaceFolder}}/tests/data/receipt/", models: list[str] = None):
    """Runs all available receipts against a model and calculates field hit rate."""
    print("\n" + "="*40)
    print("== Starting Batch LLM Benchmark ==")
    print("="*40)

    if not models:
        models = ["llama3", "phi3"] # Use defined list if none provided

    receipt_files = get_all_image_paths(data_dir)
    results = []

    for model in models:
        model_runs = []
        print(f"\n[RUNNING] Testing Model: {model}")
        for receipt_path in receipt_files:
            try:
                # Use the Generic Interface to abstract the call
                service_interface = get_model_interface(model)
                analysis, _ = run_single_receipt_test(
                    service=service_interface,
                    image_path=receipt_path,
                    expected_json=load_ground_truth(receipt_path)
                )
                hit_rate = calculate_field_accuracy(analysis, load_ground_truth(receipt_path))
                latency = measure_execution_time() # Implementation of time measurement
                model_runs.append({'hit': hit_rate, 'latency': latency})
            except Exception as e:
                print("-" * 30)
                print(f"🛑 Error processing {receipt_path}: {e}")

        # Aggregate results for the current model
        avg_accuracy = calculate_median([run['hit'] for run in model_runs]) # Pass only hit rates
        results.append({'model': model, 'median_hit_rate': avg_accuracy})

    report_summary(results)
    return get_best_performing_model(results)


def report_summary(data: list[dict]):
    """Prints the final performance table to stdout."""
    print("\n" + "="*40)
    print("--- BENCHMARK FINAL REPORT ---")
    # Determine best model before printing results row by row for better formatting
    best_model = get_best_performing_model(data)
    for entry in data:
        status = 'BEST' if entry['model'] == best_model else 'SUB'
        print(f"Model: {entry['model']:<15} | Median Hit Rate: {entry['median_hit_rate']:.2%} | <<< Status: {status}>")

def get_best_performing_model(data: list[dict]) -> str:
    """Finds and returns the model name with the highest median hit rate."""
    if not data:
        return ""
    # Sort by median_hit_rate descending and return the model name of the top entry
    best_entry = max(data, key=lambda x: x['median_hit_rate'])
    return best_entry['model']

def calculate_median(values: list[float]) -> float:
    """Calculates the median value from a list."""
    sorted_values = sorted(values)
    n = len(sorted_values)
    if n % 2 == 1:
        return sorted_values[n // 2]
    else:
        mid1 = sorted_values[n // 2 - 1]
        mid2 = sorted_values[n // 2]
        return (mid1 + mid2) / 2

if __name__ == "__main__":
    # Use the standard test data path defined in the prompt's context
    DATA_DIR = "./tests/data/receipt/"
    best_llm = run_full_llm_benchmark(data_dir=DATA_DIR)
    print("="*40)
    print(f"🚀 Recommendation: The best performing model is {best_llm}.")