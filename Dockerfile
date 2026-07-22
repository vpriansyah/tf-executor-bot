FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV WINEPREFIX=/root/.wine
ENV DISPLAY=:99
ENV PYTHONUNBUFFERED=1
ENV WINEDLLOVERRIDES="mscoree,mshtml="

# Install system dependencies, WineHQ, Xvfb, xdotool, Python Linux, unzip
RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        wget \
        curl \
        unzip \
        xdotool \
        ca-certificates \
        xvfb \
        python3 \
        python3-pip \
        netcat-openbsd \
        procps \
        gnupg2 && \
    mkdir -pm755 /etc/apt/keyrings && \
    wget -O /etc/apt/keyrings/winehq-archive.key https://dl.winehq.org/wine-builds/winehq.key && \
    wget -NP /etc/apt/sources.list.d/ https://dl.winehq.org/wine-builds/ubuntu/dists/jammy/winehq-jammy.sources && \
    apt-get update && \
    apt-get install -y --install-recommends winehq-stable || apt-get install -y --install-recommends winehq-devel || apt-get install -y wine && \
    (which wine || ln -s /usr/bin/wine64 /usr/bin/wine) && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements dan install Linux Python packages
WORKDIR /app
COPY requirements.txt /app/
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy source code aplikasi
COPY . /app/
RUN chmod +x /app/entrypoint.sh

# Port internal untuk mt5linux bridge
EXPOSE 18812

ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]
