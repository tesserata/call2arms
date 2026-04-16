FROM python:3.12-slim

WORKDIR /app

ADD ./requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

ADD ./call2arms /app/call2arms

ENV PYTHONPATH=/app

CMD ["python", "-m", "call2arms.main"]