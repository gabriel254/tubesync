#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger

from videogram.config import config
from videogram.consts import DOMAINS


def load_json(path: str | Path, default: dict | None = None) -> dict:
    path = Path(path)
    if Path(path).exists():
        logger.debug(f"Loading json from {path.as_posix()}")
        with path.open() as f:
            return json.load(f)
    logger.warning(f"{path} is not exist, return default")
    if default is None:
        return {}
    return default


def save_json(data: dict | list, path: str | Path, indent: int | None = 2) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Saving json to {path.as_posix()}")
    with path.open("w") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def parse_domain(url: str) -> str:
    logger.debug(f"Parse domain: {url}")
    parsed_url = urlparse(url)
    logger.debug(f"Parsed url: {parsed_url}")
    if not parsed_url.hostname:
        raise ValueError(f"Invalid URL: {url}")
    return parsed_url.hostname


def delete_files(path: str | Path | list | Generator):
    if isinstance(path, str):
        Path(path).unlink(missing_ok=True)
    elif isinstance(path, Path):
        path.unlink(missing_ok=True)
    elif isinstance(path, list | Generator):
        for p in path:
            delete_files(p)
    else:
        raise TypeError(f"Unsupported file type: {path}")


def check_required_keys(data: dict, keys: list[str]) -> None:
    logger.trace(f"Check required keys: {keys}, provided keys: {data.keys()}")
    valid = True
    for key in keys:
        if key not in data:
            valid = False
            logger.error(f"Required key not found: {key}")
    if not valid:
        msg = f"Required keys not found: {keys}, provided keys: {data.keys()}"
        raise KeyError(msg)


def get_cookie_file(url: str) -> str:
    domain = parse_domain(url)
    cookie_dir = Path(config.get("VIDEOGRAM_COOKIES_DIR", Path.home().joinpath(".config/videogram/cookies")))
    cookie_dir.mkdir(exist_ok=True)
    for provider, domains in DOMAINS.items():
        if domain in domains:
            cookie_file = cookie_dir.joinpath(f"{provider}.txt").as_posix()
            logger.debug(f"Cookie file: {cookie_file}")
            return cookie_file

    cookie_file = cookie_dir.joinpath(f"{domain}.txt").as_posix()
    logger.debug(f"Cookie file: {cookie_file}")
    return cookie_file
