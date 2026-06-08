# Containerized tree-sitter-analyzer MCP server (stdio transport).
#
# Built from the repo source so the image always matches the committed code.
# Used by MCP indexers (e.g. Glama) to launch and introspect the server, and
# by anyone who wants to run the MCP server in a container.
#
# Build:  docker build -t tree-sitter-analyzer-mcp .
# Run:    docker run --rm -i -v "$PWD:/work" -w /work tree-sitter-analyzer-mcp
#         (the server speaks MCP over stdio; -i keeps stdin open)
FROM python:3.12-slim

# Prebuilt tree-sitter wheels mean no compiler is needed on the slim image.
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY . /app

# Install the package with the MCP extra from the local source.
RUN pip install ".[mcp]"

# The MCP server entry point speaks JSON-RPC over stdio.
ENTRYPOINT ["tree-sitter-analyzer-mcp"]
