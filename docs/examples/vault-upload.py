import json

import requests

path = "/path/to/local/file.json"
with open(path, "w", encoding="utf-8") as file:
    json.dump({"input": "data"}, file)

# provide the desired name and format Media-Type
files = {
    "file": (
        "desired-name.json",
        open(path, "r", encoding="utf-8"),
        "application/json; charset=UTF-8"
    )
}
requests.post("https://weaver.example.com/vault", files=files)
