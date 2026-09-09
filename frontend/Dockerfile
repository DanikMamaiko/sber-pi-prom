FROM nginxinc/nginx-unprivileged:1.27-alpine

USER root
RUN addgroup -S -g 10001 sberpi && adduser -S -D -H -u 10001 -G sberpi sberpi

COPY --chown=10001:10001 frontend /usr/share/nginx/html
COPY --chown=10001:10001 deploy/nginx-container.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

# The base nginx config uses /tmp for PID and temporary files.
USER 10001:10001
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["wget", "--quiet", "--spider", "--timeout=3", "http://127.0.0.1:8080/nginx-health"]
