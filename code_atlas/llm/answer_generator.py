from ollama import Client

def query_ollama(prompt: str):
    client = Client(host='http://ollama_server:11434')
    
    try:
        response = client.chat(model='llama2', messages=[
            {
                'role': 'user',
                'content': prompt,
            },
        ])
        return response['message']['content']
    except Exception as e:
        return f"Ollama error: {str(e)}"