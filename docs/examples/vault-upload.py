import json
import requests

with open("/tmp/local.json", "w", encoding="utf-8") as file:
    json.dump({"input": "data"}, file)

# provide the desired name and format Media-Type
files = {"file": ("desired-name.json", open("/tmp/local.json", "r"), "application/json; charset=UTF-8")}
requests.post("https://weaver.example.com/vault", files=files)
