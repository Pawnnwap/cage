FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY sandboxd/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY sandboxd ./sandboxd

EXPOSE 8090
CMD ["uvicorn", "sandboxd.main:app", "--host", "0.0.0.0", "--port", "8090"]
