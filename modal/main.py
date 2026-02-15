"""Modal app entry point for TreeHacks Vector Search API.

This file defines the Modal app configuration and serves the FastAPI application
using Modal's serverless infrastructure.
"""

import modal

# Create Modal image with all required dependencies
image = (
    modal.Image.debian_slim()
    .pip_install("fastapi[standard]", "elasticsearch", "requests")
    .add_local_python_source("src")  # Single import for entire src package
)

# Create Modal app
app = modal.App("treehacks-vector-search", image=image)


@app.function(
    secrets=[
        modal.Secret.from_name("jina-secret"),
        modal.Secret.from_name("elastic-secret"),
    ],
)
@modal.asgi_app()
def web():
    """Modal ASGI app function that returns the FastAPI application."""
    from src.api import create_app

    return create_app()
