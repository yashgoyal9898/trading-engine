from __future__ import annotations

import argparse
import asyncio
import logging

import uvloop
from dotenv import load_dotenv

from src.engine import Engine
from src.infrastructure.config_loader import load_config


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def main(config_path: str) -> None:
    load_dotenv()          # .env file se CLIENT_ID, FYERS_ACCESS_TOKEN load hoga
    config = load_config(config_path)
    engine = Engine(config)
    await engine.start()
    await engine.run_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/settings.yml")
    args = parser.parse_args()

    setup_logging()
    uvloop.install()
    asyncio.run(main(args.config))