# Gunicorn configuration for elzant.com. Listens locally; put a trusted
# proxy/tunnel (Cloudflare Tunnel / Caddy) in front for HTTPS. WhiteNoise serves
# static files, so no separate web server is required. See deploy/DEPLOY.md.
# Start with: gunicorn -c deploy/gunicorn.conf.py elzant.wsgi:application

bind = "127.0.0.1:8001"
workers = 3
threads = 2
timeout = 60
graceful_timeout = 30
keepalive = 5

# Log to stdout/stderr so systemd/journald captures everything.
accesslog = "-"
errorlog = "-"
loglevel = "info"
