import sys
from pathlib import Path

# Ensure the local workspace package is imported when running from inside the package directory.
workspace_root = Path(__file__).resolve().parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from mahanai.agent import main

if __name__ == "__main__":
    main()



