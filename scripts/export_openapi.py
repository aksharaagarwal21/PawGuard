"""Write the API's OpenAPI document to a file (used to generate the TypeScript client).

Imports the app with placeholder settings so no database or network access is needed.
"""

import json
import os
import sys

os.environ.setdefault("PAWGUARD_DATABASE_URL", "postgresql://openapi:openapi@localhost/openapi")
os.environ.setdefault("PAWGUARD_SUPABASE_URL", "http://localhost:54321")
os.environ["PAWGUARD_ENV_FILE"] = os.devnull

from pawguard_api.main import create_app

out = sys.argv[1] if len(sys.argv) > 1 else "openapi.json"
with open(out, "w", encoding="utf-8", newline="\n") as f:
    json.dump(create_app().openapi(), f, indent=2, sort_keys=True, ensure_ascii=False)
    f.write("\n")
print(f"wrote {out}")
