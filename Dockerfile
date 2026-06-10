FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates gnupg git bubblewrap openssh-client && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get purge -y gnupg && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cached layer)
COPY pyproject.toml README.md LICENSE THIRD_PARTY_NOTICES.md hatch_build.py ./
RUN mkdir -p nanobot bridge && touch nanobot/__init__.py && \
    uv pip install --system --no-cache . && \
    rm -rf nanobot bridge

# Install bridge npm dependencies
COPY bridge/package.json bridge/tsconfig.json /app/bridge/
WORKDIR /app/bridge
RUN git config --global --add url."https://github.com/".insteadOf ssh://git@github.com/ && \
    git config --global --add url."https://github.com/".insteadOf git@github.com: && \
    npm install
WORKDIR /app

# Copy python/webui source and install python packages
COPY nanobot/ nanobot/
COPY webui/ webui/
RUN uv pip install --system --no-cache .

# Copy bridge source and build
COPY bridge/src/ /app/bridge/src/
WORKDIR /app/bridge
RUN npm run build
WORKDIR /app

# Create non-root user and directories
RUN useradd -m -u 1000 -s /bin/bash vidtoryagent && \
    mkdir -p /home/vidtoryagent/.vidtoryagent && \
    chown -R vidtoryagent:vidtoryagent /home/vidtoryagent /app

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

USER vidtoryagent
ENV HOME=/home/vidtoryagent
# Ensure Python prints UTF-8 (emojis in migration output on all platforms)
ENV PYTHONIOENCODING=utf-8
# SQLite WAL mode works best with this
ENV PYTHONUNBUFFERED=1

# Gateway health endpoint and optional WebUI/WebSocket channel ports
EXPOSE 18790 8765

ENTRYPOINT ["entrypoint.sh"]
CMD ["status"]
