"""contracts/openapi.json is the API contract the frontend's typed client is generated from (ADR-008).
It must match the app; regenerate on purpose with:  ENV=dev python tests/test_contract.py --write"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONTRACT = os.path.join(HERE, "..", "contracts", "openapi.json")


def current() -> dict:
    from app.main import app

    return json.loads(json.dumps(app.openapi()))


def test_the_committed_api_contract_matches_the_app():
    with open(CONTRACT) as f:
        assert json.load(f) == current(), (
            "API changed: regenerate contracts/openapi.json (see module docstring)"
        )


if __name__ == "__main__" and "--write" in sys.argv:
    sys.path.insert(0, os.path.dirname(HERE))
    with open(CONTRACT, "w") as f:
        json.dump(current(), f, indent=1, sort_keys=True)
        f.write("\n")
    print("wrote", CONTRACT)
