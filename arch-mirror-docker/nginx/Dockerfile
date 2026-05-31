FROM nginx:stable-alpine

# Remove default config
RUN rm /etc/nginx/conf.d/default.conf

# Copy our config
COPY archmirror.conf /etc/nginx/conf.d/archmirror.conf

EXPOSE 80 443
