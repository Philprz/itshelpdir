import sys
import os

# Add the src directory to sys.path so that absolute imports work correctly
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__)))
if src_path not in sys.path:
    sys.path.insert(0, src_path)
