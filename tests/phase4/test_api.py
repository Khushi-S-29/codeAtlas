from fastapi.testclient import TestClient
from code_atlas.api import app

client = TestClient(app)

def test_ask_endpoint_success():
    headers = {"X-API-KEY": "mysecret123s"}
    response = client.post("/query", json={"query": "What does add do?"}, headers=headers)
    assert response.status_code == 200

def test_ask_endpoint_empty_query():
    headers = {"X-API-KEY": "mysecret123s"}
    response = client.post("/query", json={"query": ""}, headers=headers)
    assert response.status_code == 400