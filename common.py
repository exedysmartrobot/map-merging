import subprocess
import os
import json
from pathlib import Path

MANAGER_DIR = Path(__file__).resolve().parent
print(MANAGER_DIR)


def load_json(filename):
    file_path = MANAGER_DIR / filename
    with open(file_path, "r",  encoding="utf-8") as file:
        return json.load(file)
