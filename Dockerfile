FROM python:3.11.4-alpine3.18
RUN apk update && apk upgrade
RUN python -m pip install fastapi
RUN python -m pip install "uvicorn[standard]"
WORKDIR /code
ADD ./ /code
CMD ["uvicorn","main:app","--port","99","--host","0.0.0.0"]

