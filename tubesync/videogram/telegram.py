#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from pyrogram.client import Client
from pyrogram.types import Message, ReplyParameters

from videogram.config import config, config_path
from videogram.utils import check_required_keys

if TYPE_CHECKING:
    from pyrogram.types import Message


def telegram_proxy() -> dict:
    """Set network proxy for Telegram client.

    https://docs.pyrogram.org/topics/proxy
    """
    if not config.get("VIDEOGRAM_PROXY", ""):
        return {}
    proxy = {
        "scheme": config.get("VIDEOGRAM_PROXY_SCHEME"),
        "hostname": config.get("VIDEOGRAM_PROXY_HOST"),
        "port": int(config.get("VIDEOGRAM_PROXY_PORT", 7890)),
    }
    if config.get("VIDEOGRAM_PROXY_USER", ""):
        proxy["username"] = config.get("VIDEOGRAM_PROXY_USER")
    if config.get("VIDEOGRAM_PROXY_PASS", ""):
        proxy["password"] = config.get("VIDEOGRAM_PROXY_PASS")
    logger.trace(f"set Telegram proxy: {proxy}")
    return proxy


async def init_telegram_bot() -> Client:
    """Telegram Authorization.

    docs: https://docs.pyrogram.org/topics/storage-engines
    """
    if config.get("VIDEOGRAM_TG_SESSION_STRING", ""):
        logger.debug("Use VIDEOGRAM_TG_SESSION_STRING to authorize telegram bot.")
        app = Client(
            "youtube",
            session_string=config.get("VIDEOGRAM_TG_SESSION_STRING", ""),
            in_memory=True,
            no_updates=True,
            proxy=telegram_proxy(),
        )
    elif config.get("VIDEOGRAM_TG_BOT_TOKEN", ""):
        check_required_keys(config, ["VIDEOGRAM_TG_APPID", "VIDEOGRAM_TG_APPHASH"])
        logger.debug("Use VIDEOGRAM_TG_BOT_TOKEN to authorize telegram bot.")
        bot = Client(
            "youtube",
            api_id=config.get("VIDEOGRAM_TG_APPID", ""),
            api_hash=config.get("VIDEOGRAM_TG_APPHASH", ""),
            bot_token=config.get("VIDEOGRAM_TG_BOT_TOKEN", ""),
            in_memory=True,
            no_updates=True,
            proxy=telegram_proxy(),
        )
        async with bot:
            session_string = await bot.export_session_string()
            app = Client(
                "youtube",
                session_string=session_string,  # type: ignore
                in_memory=True,
                no_updates=True,
                proxy=telegram_proxy(),
            )
        # save session_string to config
        logger.info(f"Save VIDEOGRAM_TG_SESSION_STRING to {config_path.as_posix()}")
        config["VIDEOGRAM_TG_SESSION_STRING"] = session_string
        with config_path.open("w") as f:
            json.dump(config, f, indent=2)

    else:
        msg = "No authorization method found."
        msg += "\nPlease set VIDEOGRAM_TG_SESSION_STRING (https://docs.pyrogram.org/start/auth)"
        msg += "\nor set VIDEOGRAM_TG_BOT_TOKEN & VIDEOGRAM_TG_APPID & VIDEOGRAM_TG_APPHASH"
        raise RuntimeError(msg)
    return app


async def telegram_process(current, total):
    logger.trace(f"Uploading {current/1024/1024:.1f} / {total/1024/1024:.1f} MB ({current / total:.2%})")


async def send_video_telegram(info: dict, target: str, reply_msg_id: str) -> Message | None:
    logger.info(f"Uploading video to Telegram for: {Path(info['video_path']).name} ")
    client = await init_telegram_bot()
    async with client:
        return await client.send_video(
            int(target),
            video=info["video_path"],
            caption=info["caption"],
            duration=info["duration"],
            width=info["width"],
            height=info["height"],
            supports_streaming=True,
            progress=telegram_process,
            reply_parameters=ReplyParameters(message_id=int(reply_msg_id)) if reply_msg_id else None,  # type: ignore
            thumb=info["thumb"],
        )


async def send_audio_telegram(info: dict, target: str, reply_msg_id: str) -> Message | None:
    logger.info(f"Uploading audio to Telegram for: {Path(info['audio_path']).name} ")
    client = await init_telegram_bot()
    async with client:
        return await client.send_audio(
            int(target),
            audio=info["audio_path"],
            caption=info["caption"],
            duration=info["duration"],
            performer=info.get("uploader", ""),
            title=info["title"],
            reply_parameters=ReplyParameters(message_id=int(reply_msg_id)) if reply_msg_id else None,  # type: ignore
            progress=telegram_process,
            thumb=info["thumb"],
        )
