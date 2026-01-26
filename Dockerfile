# Claude Task Scheduler - Docker Image
# Runs the scheduler daemon for executing Claude Code prompts on schedule

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (required for Claude Code CLI)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Create app user
RUN useradd -m -s /bin/bash scheduler

# Create directories
RUN mkdir -p /app /data /home/scheduler/.claude-task-scheduler
RUN chown -R scheduler:scheduler /app /data /home/scheduler

# Set working directory
WORKDIR /app

# Copy and install the scheduler CLI
COPY --chown=scheduler:scheduler pyproject.toml README.md ./
COPY --chown=scheduler:scheduler claude_task_scheduler_cli ./claude_task_scheduler_cli/

# Install the scheduler
RUN pip install --no-cache-dir .

# Switch to non-root user
USER scheduler

# Environment variables
ENV DATABASE_PATH=/data/scheduler.db
ENV PYTHONUNBUFFERED=1

# Volume for persistent data
VOLUME ["/data"]

# Volume for Claude Code config (mount from host)
VOLUME ["/home/scheduler/.claude"]

# Volume for project directories (mount from host)
VOLUME ["/projects"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD claude-task-scheduler daemon status || exit 1

# Default command - start the daemon
CMD ["claude-task-scheduler", "daemon", "start"]
