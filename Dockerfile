FROM python:3.12-slim

# Install Playwright system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-liberation \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    && rm -rf /var/lib/apt/lists/*

# Install codewiki-mcp from PyPI (pinned) + Playwright Chromium
ARG CODEWIKI_VERSION=1.3.0
RUN pip install --no-cache-dir "codewiki-mcp==${CODEWIKI_VERSION}" \
    && playwright install --with-deps chromium

# Create non-root user for runtime
RUN groupadd -r codewiki && useradd -r -g codewiki -d /home/codewiki -s /bin/false codewiki \
    && mkdir -p /home/codewiki && chown codewiki:codewiki /home/codewiki

# Environment variable defaults
ENV CODEWIKI_HARD_TIMEOUT=60
ENV CODEWIKI_MAX_RETRIES=2
ENV CODEWIKI_RESPONSE_MAX_CHARS=30000
ENV CODEWIKI_VERBOSE=false

# Run as non-root
USER codewiki
WORKDIR /home/codewiki

# Default: stdio transport
ENTRYPOINT ["codewiki-mcp"]
CMD ["--stdio"]

# For SSE transport, run:
#   docker run -p 3000:3000 codewiki-mcp --sse --port 3000
