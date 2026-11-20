import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIXTURE_PROFILE = Path(__file__).resolve().parent / "fixtures" / "profile"
