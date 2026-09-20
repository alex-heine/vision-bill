"""Wait until the e2e app answers on its public readiness endpoint."""

import sys
import time
import urllib.request

BASE_URL = "http://localhost:53625"
URL = f"{BASE_URL}/api/v1/system/ui-config"
HEALTH_URL = f"{BASE_URL}/health"
TIMEOUT_S = 300  # 5 minutes for GPC import + app startup


def main() -> int:
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            # Try the readiness endpoint first
            with urllib.request.urlopen(URL, timeout=3) as resp:
                if resp.status == 200:
                    print(f"e2e app ready at {BASE_URL}")
                    return 0
        except Exception:  # noqa: BLE001 - poll until ready
            pass

        try:
            # Fall back to health endpoint
            with urllib.request.urlopen(HEALTH_URL, timeout=3) as resp:
                if resp.status == 200:
                    print(f"e2e app healthy at {BASE_URL}")
                    return 0
        except Exception:  # noqa: BLE001 - poll until ready
            pass

        time.sleep(2)
    print(
        f"e2e app not ready after {TIMEOUT_S}s; "
        "check: docker compose -f docker-compose.e2e.yml logs",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
