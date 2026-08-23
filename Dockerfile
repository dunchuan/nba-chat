FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
# Use a current installer and the canonical package index. Some configured
# mirrors can serve an artifact whose content does not match its advertised
# sha256, which makes pip abort with "Expected sha256 ... Got ...".
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir --index-url https://pypi.org/simple -r requirements.txt

COPY . ./

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
