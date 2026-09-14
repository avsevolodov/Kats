#!/usr/bin/env python3
"""Only Git receives the answer through its private askpass pipe."""
import json
import os
import sys
from pathlib import Path
secret = json.loads(Path(os.environ["GIT_CREDENTIAL_FILE"]).read_text())
print(secret["username"] if "username" in sys.argv[1].lower() else secret["password"])
