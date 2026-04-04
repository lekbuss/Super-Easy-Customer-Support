from pathlib import Path
import runpy
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
project_root_str = str(PROJECT_ROOT)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

runpy.run_path(str(Path(__file__).with_name("main.py")), run_name="__main__")
