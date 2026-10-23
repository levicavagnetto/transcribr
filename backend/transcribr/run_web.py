"""`transcribr web`: run the web service with uvicorn."""

import uvicorn

from transcribr.api.app import create_app
from transcribr.config import load_config


def run_web() -> int:
    config = load_config()
    app = create_app(config)
    uvicorn.run(app, host="0.0.0.0", port=config.port, log_config=None, access_log=False)  # noqa: S104 - served to the shop network
    return 0
