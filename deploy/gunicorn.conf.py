# Gunicorn configuration for elzant.com (runs behind Nginx).
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
