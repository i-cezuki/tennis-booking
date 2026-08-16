import sys
from pathlib import Path

# Add the project root to sys.path so imports like 'from src.xxx import ...' work
sys.path.insert(0, str(Path(__file__).parent))
