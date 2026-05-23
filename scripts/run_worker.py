"""Background worker — pulls BatchScheduler jobs and runs them.

Run with: ``python -m scripts.run_worker`` (or via Dockerfile.worker).
"""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path

from manhuaju.api.app import create_app

_STOP = False


def _handle_signal(_signum, _frame):  # type: ignore[no-untyped-def]
    global _STOP  # noqa: PLW0603
    _STOP = True


def main() -> int:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    data_root = Path(os.getenv("MANHUAJU_API_DATA", "./api_data"))
    app = create_app(storage_root=data_root)
    batch = app.state.batch_scheduler

    poll_interval = float(os.getenv("MANHUAJU_WORKER_POLL_S", "5"))
    print(f"[worker] polling every {poll_interval}s; data={data_root}", flush=True)

    while not _STOP:
        try:
            jid = batch.run_next()
            if jid is None:
                time.sleep(poll_interval)
            else:
                print(f"[worker] ran job {jid}", flush=True)
        except KeyboardInterrupt:
            break
        except Exception as e:  # noqa: BLE001
            print(f"[worker] error: {e}", flush=True)
            time.sleep(poll_interval)
    print("[worker] shutting down", flush=True)
    try:
        batch.shutdown()
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
