import os
import re
import yt_dlp

SUPPORTED_DOMAINS = [
    r'https?://(?:www\.)?instagram\.com/[^\s]+',
    r'https?://(?:www\.)?youtube\.com/[^\s]+',
    r'https?://youtu\.be/[^\s]+',
    r'https?://(?:www\.)?twitter\.com/[^\s]+',
    r'https?://(?:www\.)?x\.com/[^\s]+',
    r'https?://(?:www\.)?pinterest\.(?:com|it|co\.uk)/[^\s]+',
    r'https?://(?:www\.)?reddit\.com/[^\s]+',
    r'https?://(?:www\.)?tiktok\.com/[^\s]+',
]

def is_media_url(text):
    if not text:
        return None
    for pattern in SUPPORTED_DOMAINS:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None

def download_media(url, output_dir="/tmp/downloads"):
    os.makedirs(output_dir, exist_ok=True)
    out_template = os.path.join(output_dir, "%(id)s.%(ext)s")
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best',
        'outtmpl': out_template,
        'max_filesize': 48 * 1024 * 1024,  # Max 48 MB (Telegram limit is 50MB)
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            if not os.path.exists(file_path):
                # Check with mp4 extension if merged
                base, _ = os.path.splitext(file_path)
                if os.path.exists(base + ".mp4"):
                    file_path = base + ".mp4"
            
            if os.path.exists(file_path):
                return {
                    "success": True,
                    "file_path": file_path,
                    "title": info.get("title", "Video"),
                    "duration": info.get("duration", 0),
                    "filesize": os.path.getsize(file_path)
                }
            else:
                return {"success": False, "error": "File not found after download."}
    except Exception as e:
        return {"success": False, "error": str(e)}

def download_audio(url, output_dir="/tmp/downloads"):
    os.makedirs(output_dir, exist_ok=True)
    out_template = os.path.join(output_dir, "%(id)s.%(ext)s")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': out_template,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'max_filesize': 48 * 1024 * 1024,
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            base, _ = os.path.splitext(file_path)
            mp3_path = base + ".mp3"
            
            target = mp3_path if os.path.exists(mp3_path) else file_path
            if os.path.exists(target):
                return {
                    "success": True,
                    "file_path": target,
                    "title": info.get("title", "Audio"),
                    "duration": info.get("duration", 0)
                }
            return {"success": False, "error": "Audio file conversion failed."}
    except Exception as e:
        return {"success": False, "error": str(e)}

