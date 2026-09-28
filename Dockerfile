FROM python:3.11
WORKDIR /code
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt
COPY . .
CMD ["gunicorn", "--workers", "2", "--threads", "4", "--timeout", "120", "-b", "0.0.0.0:7860", "app:app"]
