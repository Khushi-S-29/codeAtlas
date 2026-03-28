# 1️⃣ Base image
FROM python:3.10-slim

# 2️⃣ Set working directory
WORKDIR /app

ENV PYTHONPATH=/app

ENV TRANSFORMERS_OFFLINE=1
ENV HF_HUB_OFFLINE=0

# 3️⃣ Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 4️⃣ Upgrade pip (VERY IMPORTANT)
RUN pip install --upgrade pip

RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# 5️⃣ Copy requirements first (for caching)
COPY requirements.txt .

# 6️⃣ Install dependencies with high timeout (IMPORTANT FOR TORCH)
RUN pip install --no-cache-dir \
    --timeout 1000 \
    --retries 10 \
    -r requirements.txt

# 7️⃣ Copy full project
COPY . .

# 8️⃣ Expose API port
EXPOSE 8000

# 9️⃣ Run FastAPI app
CMD ["uvicorn", "code_atlas.api:app", "--host", "0.0.0.0", "--port", "8000"]