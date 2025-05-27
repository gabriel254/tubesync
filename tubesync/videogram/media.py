#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

import requests
from ffmpeg import FFmpeg, FFmpegError
from loguru import logger

from videogram.config import config, config_path, save_config
from videogram.consts import AUDIO_FORMATS
from videogram.utils import check_required_keys


def generate_cover(path: str) -> str:
    """Generate cover image base on media file path.

    Usually the cover image is downloaded together with the media file, with a ".webp" extension.

    Args:
        path (str): media file path

    Returns:
        str: cover path
    """
    logger.debug(f"Generate cover for: {path}")
    jpg_path = Path(path).with_suffix(".jpg")
    if jpg_path.exists():
        logger.debug(f"JPG cover image already exists: {jpg_path.as_posix()}")
        return jpg_path.as_posix()

    webp_path = Path(path).with_suffix(".webp")
    if webp_path.exists():
        logger.debug(f"Found WebP cover image: {webp_path.as_posix()}, convert to JPG ...")
        try:
            ffmpeg = FFmpeg().option("y").option("loglevel", "warning").input(webp_path).output(jpg_path)
            ffmpeg.execute()
            return jpg_path.as_posix()
        except FFmpegError as exception:
            logger.error(f"Failed to convert WebP cover image to JPG: {webp_path.as_posix()}")
            logger.error(f"Message from ffmpeg: {exception.message}")
            logger.warning("Trying next method to gernerate JPG cover image ...")

    png_path = Path(path).with_suffix(".png")
    if png_path.exists():
        logger.debug(f"Found PNG cover image: {png_path.as_posix()}, convert to JPG ...")
        try:
            ffmpeg = FFmpeg().option("y").option("loglevel", "warning").input(png_path).output(jpg_path)
            ffmpeg.execute()
            return jpg_path.as_posix()
        except FFmpegError as exception:
            logger.error(f"Failed to convert PNG cover image to JPG: {png_path.as_posix()}")
            logger.error(f"Message from ffmpeg: {exception.message}")
            logger.warning("Trying next method to gernerate JPG cover image ...")

    # For video format, generate cover image from the first frame
    if Path(path).suffix not in AUDIO_FORMATS:
        logger.debug(f"No cover image found, generate from the first frame of {path}")
        try:
            ffmpeg = FFmpeg().option("y").option("loglevel", "warning").input(path).output(jpg_path, vframes=1)
            ffmpeg.execute()
            return jpg_path.as_posix()
        except FFmpegError as exception:
            logger.error(f"Failed to convert first video frame to JPG: {png_path.as_posix()}")
            logger.error(f"Message from ffmpeg: {exception.message}")

    # For failing to generate from ffmpeg or audio format, use default cover image.
    # Download if not exists.
    default_cover = config.get("VIDEOGRAM_DEFAULT_COVER", config_path.with_name("default_cover.jpg").as_posix())
    logger.warning(f"Use default cover image: {default_cover}")

    if not Path(default_cover).exists():
        # download default cover image
        url = "https://wsrv.nl/?url=github.com/edent/SuperTinyIcons/raw/master/images/svg/apple_music.svg&output=jpg"
        logger.debug(f"Downloading defalult cover image from: {url}")
        logger.debug(f"Downloading defalult cover image to: {default_cover}")
        with requests.get(url, timeout=5) as response:
            response.raise_for_status()
            with open(default_cover, "wb") as f:
                f.write(response.content)
        config["VIDEOGRAM_DEFAULT_COVER"] = default_cover
        save_config(config)

    return default_cover


def parse_general_info(path: Path, media_format: str, link: str = "") -> dict:
    """Given a media filepath, parse necessary information for uploading to Telegram.

    Required fields:
        title: str
        video_path: str
        audio_path: str
        caption: str
        uploader: str
        duration: int
        width: int
        height: int
        thumb: str
    """
    ffprobe = FFmpeg(executable="ffprobe").input(
        path.as_posix(),
        print_format="json",  # ffprobe will output the results in JSON format
        show_streams=None,  # show stream information
    )
    metadata = json.loads(ffprobe.execute())
    check_required_keys(metadata, ["streams"])
    check_required_keys(metadata["streams"][0], ["duration"])
    caption = f"[{path.stem}]({link})" if link else path.stem
    duration = round(float(metadata["streams"][0]["duration"]))  # in seconds
    width = next(x["width"] for x in metadata["streams"] if "width" in x) if media_format == "video" else 0
    height = next(x["height"] for x in metadata["streams"] if "height" in x) if media_format == "video" else 0
    thumb = generate_cover(path.as_posix())
    return {
        "title": path.stem,
        "video_path": path.resolve().as_posix(),
        "audio_path": path.resolve().as_posix(),
        "caption": caption,
        "uploader": "",
        "duration": duration,
        "width": int(width),
        "height": int(height),
        "thumb": Path(thumb).resolve().as_posix(),
    }


def ffmpeg_split_by_size(file_path: Path, out_path: Path, split_size: int, start_time: float) -> dict:
    logger.debug(f"Split video: {file_path.as_posix()} to {out_path.as_posix()} at {start_time:.1f}s")
    try:
        ffmpeg = (
            FFmpeg()
            .option("y")
            .option("loglevel", "warning")
            .input(file_path, ss=f"{start_time*1000:.0f}ms")
            .output(out_path, acodec="copy", vcodec="copy", fs=split_size)
        )
        ffmpeg.execute()
    except FFmpegError as exception:
        logger.error(f"Failed to split video: {file_path.as_posix()}")
        logger.error(f"Message from ffmpeg: {exception.message}")
        if "Error muxing a packet" in exception.message:
            logger.warning("This is not a fatal error, continue to split the video.")
        else:
            return {"valid": False}

    ffprobe = FFmpeg(executable="ffprobe").input(
        out_path.as_posix(),
        print_format="json",  # ffprobe will output the results in JSON format
        show_streams=None,  # show stream information
    )
    metadata = json.loads(ffprobe.execute())
    duration = float(metadata["streams"][0]["duration"])
    return {"valid": True, "duration": duration}


def split_video_by_size(info: dict, split_size: str = config.get("VIDEOGRAM_TG_MAX_FILE_BYTES", "2097152000")) -> list[dict]:
    """Split video file by size.

    This is to send large video file to Telegram, which has a 2000MB limit for normal users.
    We use ffmpeg to split the video file into smaller parts.
    But ffmpeg do not support split by size accurately at the specific size.
    So we need to reduce the split size a little bit to make sure the split size is less than the limit.

    Args:
        info (dict): video info
        split_size (str, optional): split size in bytes. Defaults to 2000MB.

    Returns:
        list[dict]: list of video info
    """
    file_path = Path(info["video_path"])
    cover_path = generate_cover(file_path.as_posix())
    file_size = file_path.stat().st_size
    if file_size <= int(split_size):
        return [info]

    reduced_split_size = int(split_size) - 50 * 1024 * 1024  # reduce split size a little bit (50MB)
    logger.info(f"Video file size: {file_size/1024/1024:.1f} MB, split size: {int(reduced_split_size)/1024/1024:.1f} MB")
    file_stem = file_path.stem
    num_split_parts = (file_size // reduced_split_size) + 1
    logger.info(f"Split video file: {file_path.name} into {num_split_parts} parts.")
    results = []
    start_time = 0
    for idx in range(num_split_parts):
        out_path = file_path.with_stem(f"{file_stem}_{idx:02}")
        splited_info = ffmpeg_split_by_size(file_path, out_path, reduced_split_size, start_time)
        if splited_info["valid"]:
            start_time += splited_info["duration"]
            new_info = info.copy()
            new_info.update(
                {
                    "video_path": out_path.as_posix(),
                    "duration": round(splited_info["duration"]),
                    "caption": f"{info['caption']}-P{idx+1}",
                    "thumb": cover_path,
                }
            )
            results.append(new_info)
    return results
