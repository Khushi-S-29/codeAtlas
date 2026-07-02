import requests

API_URL = "http://localhost:8002/query"
API_KEY = "mysecret123s"

print("CodeAtlas Chat")
print("Type 'exit' to quit.\n")

while True:
    query = input("Ask: ")

    if query.lower() in ["exit", "quit"]:
        break

    try:
        response = requests.post(
            API_URL,
            headers={
                "Content-Type": "application/json",
                "X-API-KEY": API_KEY
            },
            json={
                "query": query,
                "k": 5
            }
        )

        response.raise_for_status()
        data = response.json()

        print("\nAnswer:")
        print(data.get("answer", "No answer returned"))
        print()

    except Exception as e:
        print(f"\nError: {e}\n")