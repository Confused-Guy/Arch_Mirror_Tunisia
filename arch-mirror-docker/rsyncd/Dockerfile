FROM alpine:latest

RUN apk add --no-cache rsync tzdata

COPY rsyncd.conf /etc/rsyncd.conf

EXPOSE 873

ENTRYPOINT ["rsync", "--daemon", "--no-detach", "--config=/etc/rsyncd.conf"]
