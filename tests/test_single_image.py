#!/usr/bin/env python3
import json
import requests

url = "http://localhost:8080/api/v1/receipts/analyze-image"
#file_path = "./data/bauhaus.jpeg"
file_path = "./data/very-long-hit.png"

params = {"model_id": "gemma4:e4b"}

with open(file_path, "rb") as f:
    files = {"receipt": (file_path, f, "image/jpeg")}
    response = requests.post(url, files=files, params=params, )

print(response)
print(json.dumps(response.json(), indent=2))
