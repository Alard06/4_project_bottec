FROM python:3.13-slim

WORKDIR /app


RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    wget \
    xz-utils \
    supervisor \
    nginx \
    && wget -q https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz \
    && tar xf ffmpeg-release-amd64-static.tar.xz \
    && mv ffmpeg-*-static/ffmpeg /usr/local/bin/ \
    && mv ffmpeg-*-static/ffprobe /usr/local/bin/ \
    && rm -rf ffmpeg-* \
    && apt-get remove -y wget xz-utils \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*


COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


COPY . .


COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY nginx.conf /etc/nginx/nginx.conf


RUN python manage.py collectstatic --noinput

EXPOSE 80


CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
