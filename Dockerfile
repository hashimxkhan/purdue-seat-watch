FROM python:3.12-slim

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir -e ".[web]"

# Railway sets $PORT at runtime. This default CMD runs the web service; the
# worker service overrides it with its own Start Command in the Railway
# dashboard (python -m purdue_seat_watch.worker).
CMD ["sh", "-c", "python -m uvicorn purdue_seat_watch.web:app --host 0.0.0.0 --port $PORT"]
