FROM nginx:stable-alpine

# Remove default config
RUN rm /etc/nginx/conf.d/default.conf

# Custom main config (fd limits, aio, open_file_cache, etc.)
COPY nginx.conf /etc/nginx/nginx.conf

# Copy our config
COPY archmirror.conf /etc/nginx/conf.d/archmirror.conf

EXPOSE 80 443
