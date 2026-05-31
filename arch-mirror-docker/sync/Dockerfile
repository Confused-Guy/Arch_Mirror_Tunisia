FROM alpine:latest

# rsync is all we need
RUN apk add --no-cache rsync tzdata

# Copy sync script
COPY archmirror-sync.sh /usr/local/bin/archmirror-sync.sh
RUN chmod +x /usr/local/bin/archmirror-sync.sh

# Copy entrypoint that handles the cron scheduling
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
