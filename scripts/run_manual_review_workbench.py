"""Launch the local JCFB V4 manual review workbench."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.manual_review_workbench.__main__ import main


if __name__ == "__main__":
    main()
