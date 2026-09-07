from __future__ import annotations

import argparse

from .core import STAGING, Workbench
from .server import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local JCFB V4 human visual review workbench")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--staging", default=str(STAGING))
    parser.add_argument("--output", default=None)
    parser.add_argument("--reviewer-id", default=None, help="Displayed launch-time identity; UI still persists its own reviewer field")
    args = parser.parse_args()
    workbench = Workbench(staging=args.staging, output=args.output)
    if args.reviewer_id:
        state = workbench.session_state()
        state["reviewer_id"] = args.reviewer_id
        from .core import _write_json
        _write_json(workbench.output / "review_session_state.json", state)
    serve(workbench, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
