#! /usr/bin/env python
# -*- coding: utf-8 -*-
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

from videogram.asynctyper import AsyncTyper
from videogram.config import config, config_path, default_config, save_config
from videogram.consts import AUDIO_FORMATS, DOMAINS
from videogram.media import parse_general_info, split_video_by_size
from videogram.telegram import send_audio_telegram, send_video_telegram
from videogram.utils import delete_files, parse_domain
from videogram.ytdlp import ytdlp_download, ytdlp_struct_info

app = AsyncTyper()


@app.command()
def download(
    url: Annotated[str, typer.Argument(metavar="link")],
    save_dir: Annotated[str, typer.Option(metavar="Path", help="Save directory of the downloaded files")] = ".",
    *,
    download_video: Annotated[bool, typer.Option(help="Whether to download video file.", show_default=True)] = True,
    split_video: Annotated[bool, typer.Option(help="Whether to split large video file.", show_default=True)] = False,
    playlist: Annotated[bool, typer.Option(help="Whether to parse playlist.", show_default=True)] = True,
    use_cookie: Annotated[bool, typer.Option(help="Whether to use cookie file.", show_default=True)] = True,
) -> dict:
    results = {
        "args": {
            "url": url,
            "download_video": download_video,
            "split_video": split_video,
            "playlist": playlist,
            "use_cookie": use_cookie,
        },
        "video_info": [],
        "audio_info": [],
    }
    logger.info(f"Download: {url}")
    domain = parse_domain(url)

    # YouTube
    if domain in DOMAINS["youtube"]:
        logger.info("Downloading from YouTube ...")
        download_info = ytdlp_download(url, Path(save_dir), use_cookie=use_cookie, playlist=playlist, download_video=download_video)
    # Bilibili
    elif domain in DOMAINS["bilibili"]:
        logger.info("Downloading from Bilibili ...")
        download_info = ytdlp_download(url, Path(save_dir), use_cookie=use_cookie, playlist=playlist, download_video=download_video)
    else:
        logger.error(f"Unsupported domain: {domain}")
        raise typer.Exit(code=1)

    info_list = [ytdlp_struct_info(info) for info in download_info]
    results["audio_info"].extend(info_list)
    if download_video and split_video:
        [results["video_info"].extend(split_video_by_size(info)) for info in info_list]
    elif download_video:
        results["video_info"].extend(info_list)
    return results


@app.command()
async def upload(
    path: Annotated[Path, typer.Argument(exists=True)],
    link: Annotated[str, typer.Option(metavar="URL", help="Website url of this file")] = "",
    tg_id: Annotated[str, typer.Option(metavar="TG-ID", help="Sync Telegram target")] = config.get("VIDEOGRAM_TG_TARGET_ID", ""),
) -> None:
    logger.debug(f"Uploading: {path.as_posix()}")
    if path.suffix in {".mp4"}:
        info = parse_general_info(path, link=link, media_format="video")
        await send_video_telegram(info, tg_id)
    elif path.suffix in AUDIO_FORMATS:
        info = parse_general_info(path, link=link, media_format="audio")
        await send_audio_telegram(info, tg_id)
    else:
        logger.error(f"Unsupported file format: {path.suffix}")
        raise typer.Exit(code=1)


@app.command()
async def sync(
    url: Annotated[str, typer.Argument(metavar="link")],
    tg_id: Annotated[str, typer.Option(metavar="TG-ID", help="Sync Telegram target")] = config.get("VIDEOGRAM_TG_TARGET_ID", ""),
    *,
    reply_msg_id: Annotated[str, typer.Option(metavar="ReplyID", help="Reply to message ID")] = "",
    sync_video: Annotated[bool, typer.Option(help="Sync video file.", show_default=True)] = True,
    sync_audio: Annotated[bool, typer.Option(help="sync audio file.", show_default=True)] = True,
    clean: Annotated[bool, typer.Option(help="Clean up downloaded files.", show_default=True)] = True,
    playlist: Annotated[bool, typer.Option(help="Whether to parse playlist.", show_default=True)] = True,
    use_cookie: Annotated[bool, typer.Option(help="Whether to use cookie file.", show_default=True)] = True,
) -> dict:
    logger.info(f"Sync: {url}")
    results = {
        "args": {
            "url": url,
            "telegram_target": int(tg_id),
            "sync_video": sync_video,
            "sync_audio": sync_audio,
        },
        "video_info": [],
        "audio_info": [],
        "video_messages": [],  # response from Telegram
        "audio_messages": [],  # response from Telegram
    }
    # Download first
    download_results = download(url, use_cookie=use_cookie, playlist=playlist, download_video=sync_video, split_video=True)
    results["video_info"] = download_results["video_info"]
    results["audio_info"] = download_results["audio_info"]

    # Upload to Telegram
    logger.info(f"Uploading to Telegram ChatID: {tg_id}")
    if sync_video:
        # Generate a list of files to upload, split large video files if needed.
        for idx, video_info in enumerate(download_results["video_info"]):
            logger.info(f"Uploading video {idx+1}/{len(download_results['video_info'])}")
            msg = await send_video_telegram(video_info, tg_id, reply_msg_id)
            results["video_messages"].append(msg)
    if sync_audio:
        for idx, audio_info in enumerate(download_results["audio_info"]):
            logger.info(f"Uploading video {idx+1}/{len(download_results['audio_info'])}")
            msg = await send_audio_telegram(audio_info, tg_id, reply_msg_id)
            results["audio_messages"].append(msg)

    # Cleanup downloaded files
    if clean:
        logger.info("Clean up downloaded files.")
        thumb_path = video_info["thumb"] if sync_video else audio_info["thumb"]
        prefix = Path(thumb_path).stem
        trash_files = [p for p in Path(".").glob("**/*") if p.stem.startswith(prefix)]
        delete_files(trash_files)
    return results


def config_keys():
    return default_config.keys()


config_app = typer.Typer(no_args_is_help=True)
app.add_typer(config_app, name="config")


@config_app.command("info")
def config_info():
    print(f"{typer.style('VIDEOGRAM_CONFIG_FILE', fg=typer.colors.BLUE)}: {typer.style(config_path.as_posix(), fg=typer.colors.YELLOW)}")
    for k, v in sorted(config.items()):
        key = typer.style(k, fg=typer.colors.BLUE)
        value = typer.style(v, fg=typer.colors.YELLOW)
        print(f"{key}: {value}")


@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="Config key", autocompletion=config_keys)],
    value: Annotated[str, typer.Argument(help="Config value")],
):
    logger.info(f"Set {typer.style(key, fg=typer.colors.BLUE)} = {typer.style(value, fg=typer.colors.YELLOW)}")
    config[key] = value
    save_config(config)


@config_app.command("delete")
def config_delete(key: Annotated[str, typer.Argument(help="Config key", autocompletion=config_keys)]):
    logger.info(f"Delete configuration key: {typer.style(key, fg=typer.colors.BLUE)}")
    if key in config:
        del config[key]
        save_config(config)


if __name__ == "__main__":
    app()
