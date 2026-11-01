"""Entry point of the image: `python -m dpdpkit.server`."""

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "dpdpkit.server.app:create_app",
        factory=True,
        host=os.environ.get("DPDPKIT_HOST", "0.0.0.0"),  # listens inside the container
        port=int(os.environ.get("DPDPKIT_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
