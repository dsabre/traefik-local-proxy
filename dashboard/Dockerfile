FROM python:3.12-alpine

WORKDIR /app
COPY main.py /app/main.py
COPY static /app/static

EXPOSE 8000
CMD ["python", "-u", "main.py"]
