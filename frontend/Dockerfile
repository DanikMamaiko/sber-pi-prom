FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY --chown=101:101 frontend /usr/share/nginx/html
COPY --chown=101:101 deploy/nginx-container.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
