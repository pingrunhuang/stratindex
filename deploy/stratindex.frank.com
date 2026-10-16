# StratIndex — copy to /etc/nginx/sites-available/stratindex.frank.com
# then: sudo ln -s /etc/nginx/sites-available/stratindex.frank.com /etc/nginx/sites-enabled/
#      sudo nginx -t && sudo systemctl reload nginx
# App: gunicorn/flask on 127.0.0.1:5055
# Env on app: STRATINDEX_PUBLIC_BASE_URL=https://stratindex.frank.com
#             STRATINDEX_ADMIN_PASSWORD=...
#             STRATINDEX_SECRET_KEY=...
#             STRATINDEX_INGEST_TOKEN=...

upstream stratindex_app {
    server 127.0.0.1:5055;
    keepalive 8;
}

server {
    listen 80;
    listen [::]:80;
    server_name stratindex.frank.com;

    # Redirect HTTP → HTTPS (enable after certbot, or use Cloudflare Flexible)
    # return 301 https://$host$request_uri;

    client_max_body_size 4m;

    location / {
        proxy_pass http://stratindex_app;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_connect_timeout 10s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Optional: serve static directly (uncomment if you put a root path)
    # location /static/ {
    #     alias /var/www/stratindex/static/;
    #     expires 7d;
    #     add_header Cache-Control "public";
    # }
}

# HTTPS — after: sudo certbot --nginx -d stratindex.frank.com
# server {
#     listen 443 ssl http2;
#     listen [::]:443 ssl http2;
#     server_name stratindex.frank.com;
#
#     ssl_certificate     /etc/letsencrypt/live/stratindex.frank.com/fullchain.pem;
#     ssl_certificate_key /etc/letsencrypt/live/stratindex.frank.com/privkey.pem;
#     include /etc/letsencrypt/options-ssl-nginx.conf;
#     ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
#
#     client_max_body_size 4m;
#
#     location / {
#         proxy_pass http://stratindex_app;
#         proxy_http_version 1.1;
#         proxy_set_header Host $host;
#         proxy_set_header X-Real-IP $remote_addr;
#         proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
#         proxy_set_header X-Forwarded-Proto https;
#         proxy_set_header Connection "";
#         proxy_connect_timeout 10s;
#         proxy_send_timeout 60s;
#         proxy_read_timeout 60s;
#     }
# }
