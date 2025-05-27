#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger


def get_config_path() -> Path:
    if "VIDEOGRAM_CONFIG_FILE" in os.environ:
        config_path = Path(os.environ["VIDEOGRAM_CONFIG_FILE"])
        config_path.parent.mkdir(parents=True, exist_ok=True)
    elif "XDG_CONFIG_HOME" in os.environ:
        config_path = Path(os.environ["XDG_CONFIG_HOME"]) / "videogram" / "config.json"
    else:
        config_path = Path("~/.config/videogram/config.json").expanduser()
    logger.trace(f"Config file path: {config_path.as_posix()}")
    return config_path


config_path = get_config_path()

default_config = {
    # General
    "VIDEOGRAM_LOG_LEVEL": "INFO",
    "VIDEOGRAM_DEFAULT_COVER": "",  # default cover image if not found
    "VIDEOGRAM_PROXY": "",  # network proxy
    "VIDEOGRAM_COOKIES_DIR": config_path.parent.joinpath("cookies").as_posix(),  # directory to store cookies
    # YouTube
    "VIDEOGRAM_YT_LANG": "en",  # prefered language
    # Telegram
    "VIDEOGRAM_TG_APPID": "",  # https://docs.pyrogram.org/start/setup
    "VIDEOGRAM_TG_APPHASH": "",
    "VIDEOGRAM_TG_BOT_TOKEN": "",
    "VIDEOGRAM_TG_SESSION_STRING": "",  # https://docs.pyrogram.org/topics/storage-engines
    "VIDEOGRAM_TG_TARGET_ID": "",  # Sync to which Telegram chat
    "VIDEOGRAM_TG_MAX_FILE_BYTES": "2097152000",  # Telegram max file size, default to 2000MB
}


def save_config(data: dict) -> None:
    config_file = get_config_path()
    with config_file.open("w") as f:
        json.dump(data, f, indent=2)


def load_config() -> dict:
    config_file = get_config_path()
    if not config_file.exists():
        logger.warning(f"Config file not found, create an empty one at {config_file.as_posix()}")
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.touch(mode=0o600)
        with config_file.open("w") as f:
            json.dump(default_config, f, indent=2)

    # load from config file
    with config_file.open() as f:
        file_config = json.load(f)
    # load from environment variables
    env_config = {k: v for k, v in os.environ.items() if k.startswith("VIDEOGRAM_")}

    # overwrite default config with file and env config
    config = default_config
    config.update(file_config)
    config.update(env_config)

    # setup logger
    logger.remove()  # Remove default handler.
    logger.add(
        sys.stderr,
        level=config.get("VIDEOGRAM_LOG_LEVEL", "INFO").upper(),
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green>| <level>{level: <7}</level> |<cyan>{function: ^30}</cyan>:<cyan>{line: >4}</cyan> - <level>{message}</level>",
    )

    # handle network proxy if VIDEOGRAM_PROXY is not set in the config file.
    if config.get("VIDEOGRAM_PROXY"):
        logger.debug(f"Found network proxy in config file: {config['VIDEOGRAM_PROXY']}")
        logger.debug(f"Use network proxy: {config['VIDEOGRAM_PROXY']}")
        parsed_proxy = urlparse(config["VIDEOGRAM_PROXY"])
        config["VIDEOGRAM_PROXY_SCHEME"] = str(parsed_proxy.scheme)
        config["VIDEOGRAM_PROXY_USER"] = str(parsed_proxy.username)
        config["VIDEOGRAM_PROXY_PASS"] = str(parsed_proxy.password)
        config["VIDEOGRAM_PROXY_HOST"] = str(parsed_proxy.hostname)
        config["VIDEOGRAM_PROXY_PORT"] = str(parsed_proxy.port)
    if not config.get("VIDEOGRAM_PROXY"):
        logger.debug("Network proxy in not set in config file, detecting from environment variables ...")
        # set proxy via environment variables, using the following order
        for proxy in ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
            if proxy in os.environ:
                logger.debug(f"Found {proxy} in environment variables, use {os.environ[proxy]} as network proxy")
                config["VIDEOGRAM_PROXY"] = os.environ[proxy]
                parsed_proxy = urlparse(os.environ[proxy])
                config["VIDEOGRAM_PROXY_SCHEME"] = str(parsed_proxy.scheme)
                config["VIDEOGRAM_PROXY_USER"] = str(parsed_proxy.username)
                config["VIDEOGRAM_PROXY_PASS"] = str(parsed_proxy.password)
                config["VIDEOGRAM_PROXY_HOST"] = str(parsed_proxy.hostname)
                config["VIDEOGRAM_PROXY_PORT"] = str(parsed_proxy.port)
                break
            logger.debug(f"{proxy} is not set in environment variables.")
        logger.debug(f"Current network proxy: {config.get('VIDEOGRAM_PROXY', 'None')}")
    return config


config = load_config()
