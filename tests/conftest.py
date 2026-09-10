import os
import sys

# The application lives in src/ and imports its siblings as top-level modules.
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, src_dir)
