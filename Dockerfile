FROM alpine:3.11
EXPOSE 8080

WORKDIR /root
RUN apk update
RUN apk add --no-cache uwsgi-python python3 uwsgi py3-setuptools build-base python3-dev py3-pillow
COPY . .
RUN pip3 install --no-cache-dir -r requirements.txt
CMD [ "uwsgi", "--ini", "start.ini"]


