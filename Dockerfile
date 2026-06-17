FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates git bubblewrap openssh-client && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cached layer)
COPY pyproject.toml README.md LICENSE ./
RUN mkdir -p nanobot && touch nanobot/__init__.py && \
    uv pip install --system --no-cache . && \
    rm -rf nanobot

# Copy Python source and install Python packages
COPY nanobot/ nanobot/
RUN uv pip install --system --no-cache .

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

# Gateway health endpoint
EXPOSE 18790

ENTRYPOINT ["entrypoint.sh"]
CMD ["status"]
