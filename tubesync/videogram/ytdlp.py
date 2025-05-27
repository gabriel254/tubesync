#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from loguru import logger
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError, YoutubeDLError

from videogram.config import config
from videogram.consts import AUDIO_FORMATS
from videogram.media import generate_cover
from videogram.utils import check_required_keys, get_cookie_file


def ytdlp_extract_info(
    url: str,
    *,
    use_cookie: bool = True,
    playlist: bool = True,
    process: bool = False,
) -> list[dict]:
    """Extract info from the given URL.

    Args:
        url (str): Url of the video.
        use_cookie (bool, optional): Whether to use cookie file. Defaults to True.
        playlist (bool, optional): Whether to parse playlist. Defaults to True.
        process (bool, optional): Whether to resolve all unresolved references (URLs, playlist items).

    Returns:
        list[dict]: List of extracted info.
    """
    cookie_file = get_cookie_file(url)
    ydl_opts = {
        "simulate": True,
        "skip_download": True,
        "proxy": config.get("VIDEOGRAM_YTDLP_PROXY"),
        "extractor_args": {"youtube": {"lang": [config.get("VIDEOGRAM_YT_LANG", "en")]}},
        "ignore_no_formats_error": True,
        "retries": 50,
        "nocheckcertificate": True,
        "source_address": "0.0.0.0",  # force-ipv4
        "cookiefile": cookie_file if use_cookie and Path(cookie_file).exists() else None,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info: dict = ydl.extract_info(url, download=False, process=process)  # type: ignore
    except ExtractorError as e:
        logger.error(f"ExtractorError url: {url}")
        logger.error(f"ExtractorError message: {e.msg}")
        raise
    except DownloadError as e:
        logger.error(f"DownloadError url: {url}")
        logger.error(f"DownloadError message: {e.msg}")
        raise
    except YoutubeDLError as e:
        logger.error(f"YoutubeDLError url: {url}")
        logger.error(f"YoutubeDLError message: {e.msg}")
        raise
    except Exception as e:
        logger.error(e)
        raise

    if not playlist or info.get("_type") != "playlist":
        logger.info(f"Extracted info for: {info.get('title', url)}")
        return [info]

    # if playlist, extract all entries
    entries = []
    for x in info["entries"]:
        entries.extend(list(x["entries"]))
    logger.info(f"Found {len(entries)} entries in playlist")
    return [ytdlp_extract_info(x["url"], playlist=False, process=process)[0] for x in entries]


def ytdlp_download(url: str, save_dir: Path, *, use_cookie: bool = True, playlist: bool = True, download_video: bool = True) -> list[dict]:
    cookie_file = get_cookie_file(url)
    ydl_opts = {
        "paths": {"home": save_dir.resolve().as_posix()},
        "simulate": False,
        "skip_download": False,
        "keepvideo": True,
        "format": "m4a/bestaudio/best" if not download_video else video_selector,
        "writethumbnail": True,
        "trim_file_name": 60,  # filesystem limit for filename is 255 bytes. UFT-8 char is 1-4 bytes.
        "proxy": config.get("VIDEOGRAM_YTDLP_PROXY"),
        "extractor_args": {"youtube": {"lang": [config.get("VIDEOGRAM_YT_LANG", "en")]}},
        "ignore_no_formats_error": False,
        "live_from_start": True,
        "retries": 50,
        "nocheckcertificate": True,
        "source_address": "0.0.0.0",  # force-ipv4
        "outtmpl": "%(title)s.%(ext)s",
        "cookiefile": cookie_file if use_cookie and Path(cookie_file).exists() else None,
        "noplaylist": not playlist,
    }
    logger.debug(f"Downloading {url} to {save_dir.resolve().as_posix()}")
    save_dir.mkdir(exist_ok=True)
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info: dict = ydl.extract_info(url, download=True, process=True)  # type: ignore
    except YoutubeDLError as e:
        logger.error(f"Failed to download for: {url}")
        logger.error(f"Error message: {e.msg}")
        raise
    except Exception as e:
        logger.error(e)
        raise

    if not playlist or info.get("_type") != "playlist":
        logger.info(f"Downloaded to: {info['requested_downloads'][0]['filepath']}")
        return [info]

    # if playlist, return all entries
    for entry in info["entries"]:
        logger.info(f"Downloaded to: {entry['requested_downloads'][0]['filepath']}")
    return info["entries"]


def video_selector(ctx):
    """Select the best format.

    For the best compatibility, we choose .mp4 extension with AVC codec for video, .m4a extension for audio.
    """
    # formats are already sorted worst to best
    formats = ctx.get("formats")[::-1]
    if not formats:
        raise YoutubeDLError("No format found.")

    logger.trace(f"Choose best format from {len(formats)} extracted formats")
    # acodec='none' means there is no audio
    # find compatible extension, VP9 is not supported by iOS, use AVC instead
    all_videos = [f for f in formats if f.get("video_ext", "").lower() != "none"]
    all_audios = [f for f in formats if f.get("audio_ext", "").lower() != "none"]
    videos = [f for f in all_videos if f.get("video_ext", "").lower() == "mp4" and f.get("acodec", "").lower() == "none" and f.get("vcodec", "").lower().startswith("avc")]
    audios = [f for f in all_audios if (f.get("resolution", "").lower() == "audio only" and f.get("audio_ext", "").lower() == "m4a")]
    logger.trace(f"Found {len(videos)} video formats")
    logger.trace(f"Found {len(audios)} video formats")

    # # if no compatible format found, fallback to the best format
    # if not videos:
    #     videos = all_videos
    # if not audios:
    #     audios = all_audios

    if not videos and not audios:
        raise YoutubeDLError("No video and audio format found.")
    elif not videos:
        best_audio = audios[0]
        logger.debug(f"Use audio format: {best_audio['format']}")
        yield {
            "format_id": f"{best_audio['format_id']}",
            "ext": best_audio["ext"],
            "requested_formats": [best_audio],
            "protocol": f"{best_audio['protocol']}",
        }
    elif not audios:
        best_video = videos[0]
        logger.debug(f"Use video format: {best_video['format']}")
        yield {
            "format_id": f"{best_video['format_id']}",
            "ext": best_video["ext"],
            "requested_formats": [best_video],
            "protocol": f"{best_video['protocol']}",
        }
    else:
        best_video = next((x for x in videos if x.get("format_id", "") == "299"), videos[0])  # prefer 299
        best_audio = next((x for x in audios if x.get("format_id", "") == "140"), audios[0])  # prefer 140
        logger.debug(f"Use video format: {best_video['format']}")
        logger.debug(f"Use audio format: {best_audio['format']}")
        yield {
            "format_id": f"{best_video['format_id']}+{best_audio['format_id']}",
            "ext": best_video["ext"],
            "requested_formats": [best_video, best_audio],
            "protocol": f"{best_video['protocol']}+{best_audio['protocol']}",
        }


def ytdlp_struct_info(info: dict) -> dict:
    """Given yt-dlp download info, parse necessary information and return a predefined structure.

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
    check_required_keys(info, ["title", "requested_downloads", "upload_date", "webpage_url", "duration"])
    video_path = get_filepath(info, "video")
    audio_path = get_filepath(info, "audio")

    if video_path:
        thumb = generate_cover(video_path)
        width = next(x["width"] for x in info["requested_downloads"][0]["requested_formats"] if f".{x['ext']}" not in AUDIO_FORMATS)
        height = next(x["height"] for x in info["requested_downloads"][0]["requested_formats"] if f".{x['ext']}" not in AUDIO_FORMATS)
    else:
        thumb = generate_cover(audio_path)
        width = 0
        height = 0

    # set uploader
    if "uploader" not in info:
        if "series" in info:
            info["uploader"] = info["series"]
        elif "extractor" in info:
            info["uploader"] = info["extractor"]
        else:
            info["uploader"] = "Unknown"

    compact_uploader = info["uploader"].strip().replace(" ", "_").replace(".", "_").replace("-", "_").replace("/", "_")
    # clean up url tracking parameters
    info = remove_url_tracking(info)

    return {
        "title": info["title"],
        "video_path": Path(video_path).resolve().as_posix(),
        "audio_path": Path(audio_path).resolve().as_posix(),
        "caption": f"[{info['title']}]({info['webpage_url']})\n#{compact_uploader} #{info['upload_date']}",
        "uploader": info["uploader"],
        "duration": round(float(info["duration"])),
        "width": int(width),
        "height": int(height),
        "thumb": Path(thumb).resolve().as_posix(),
    }


def get_filepath(info: dict, media_format: str = "video") -> str:
    """Get the file path of the media file.

    Args:
        info (dict): yt-dlp download info
        media_format (str, optional): "video" or "audio". Defaults to "video".

    Returns:
        str: file path
    """
    final_path = info["requested_downloads"][0]["filepath"]
    logger.trace(f"Get {media_format} filepath based on downloaded file: {final_path}")

    # video
    if media_format == "video":
        if f".{info['requested_downloads'][0]['ext']}" not in AUDIO_FORMATS:
            logger.info(f"Use {media_format} filepath: {final_path}")
            return final_path
        logger.warning(f"Not a valid video format: {final_path}")
        return ""

    # audio
    # if download without video format, the final path is already an audio file.
    if Path(final_path).suffix in AUDIO_FORMATS:
        logger.info(f"Use {media_format} filepath: {final_path}")
        return final_path

    # if download with video format, find the corresponding audio format
    requested_formats = info["requested_downloads"][0]["requested_formats"]
    audios = [x for x in requested_formats if x["audio_ext"] != "none" and f".{x['audio_ext']}" in AUDIO_FORMATS]
    if len(audios) != 1:
        logger.warning("No audio file found")
        return ""
    audio_ext = audios[0]["audio_ext"]
    format_id = audios[0]["format_id"]
    audio_path = Path(final_path).with_suffix(f".f{format_id}.{audio_ext}")
    logger.debug(f"Found audio filepath: {audio_path}")
    # create a symmlink to the audio file without format_id
    strip_id_path = Path(final_path).with_suffix(f".{audio_ext}")
    strip_id_path.unlink(missing_ok=True)
    strip_id_path.symlink_to(audio_path)
    logger.info(f"Symlink {audio_ext} file to: {strip_id_path.name}")
    return strip_id_path.as_posix()


def remove_url_tracking(info: dict) -> dict:
    """Remove tracking parameters from the webpage_url.

    Args:
        info (dict): yt-dlp download info

    Returns:
        dict: updated info
    """
    if info.get("extractor") == "BiliBili":
        bid = info.get("webpage_url_basename", "")
        if "_p" in info.get("display_id", ""):  # this is a part of a series
            pid = info["display_id"].split("_p")[-1]
            bid = f"{bid}?p={pid}".removesuffix("?p=1")  # remove p=1
        info["webpage_url"] = f"https://www.bilibili.com/video/{bid}"
    return info
