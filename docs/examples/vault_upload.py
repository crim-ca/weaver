import json

import requests

PATH = "/path/to/local/file.json"
with open(PATH, "w", encoding="utf-8") as file:
    json.dump({"input": "data"}, file)

# provide the desired name and format Media-Type
files = {
    "file": (
        "desired-name.json",
        open(PATH, "r", encoding="utf-8"),
        "application/json; charset=UTF-8"
    )
}
requests.post("https://weaver.example.com/vault", files=files, timeout=5)
