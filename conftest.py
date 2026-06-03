"""pytest conftest — thêm project root vào sys.path."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
