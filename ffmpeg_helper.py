import os
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

def get_ffmpeg_binary() -> str:
    """Finds FFmpeg executable in PATH or via imageio_ffmpeg."""
    path_ffmpeg = shutil.which("ffmpeg")
    if path_ffmpeg:
        return path_ffmpeg
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        logger.error(f"Could not locate FFmpeg: {e}")
        raise RuntimeError(
            "FFmpeg executable not found. Please install FFmpeg or install imageio-ffmpeg."
        )

def convert_audio_to_video(
    thumbnail_path: Path,
    audio_path: Path,
    output_path: Path
) -> Path:
    """
    Combines a static thumbnail and an audio file into an optimized MP4 video.
    
    Uses:
    - -tune stillimage: optimizes x264 for static images
    - -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2": prevents odd-dimension failures with H.264
    - -pix_fmt yuv420p: ensures universal YouTube decoding compatibility
    - -shortest: ends the video when the audio ends
    - -movflags +faststart: optimizes MP4 for immediate streaming
    """
    ffmpeg_exe = get_ffmpeg_binary()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg_exe,
        "-y",                             # Overwrite output if exists
        "-loop", "1",                     # Loop the static image
        "-framerate", "1",                # 1 fps is sufficient for a static image
        "-i", str(thumbnail_path),        # Thumbnail input
        "-i", str(audio_path),            # Audio input
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # Ensure even dimensions
        "-c:v", "libx264",                # H.264 video codec
        "-tune", "stillimage",            # Optimize for static picture
        "-preset", "veryfast",            # Fast encoding
        "-crf", "28",                     # Low file size, great quality for still image
        "-c:a", "aac",                    # AAC audio codec
        "-b:a", "192k",                   # High quality audio bitrate
        "-pix_fmt", "yuv420p",            # Standard 4:2:0 chroma subsampling for YouTube
        "-shortest",                      # Stop writing when audio ends
        "-movflags", "+faststart",        # Relocate moov atom to start of file
        str(output_path)
    ]

    logger.info(f"Rendering MP4: '{audio_path.name}' + '{thumbnail_path.name}' -> '{output_path.name}'")
    
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    if result.returncode != 0:
        logger.error(f"FFmpeg error: {result.stderr}")
        raise RuntimeError(f"FFmpeg conversion failed: {result.stderr[-400:]}")

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Output video was not generated or is empty: {output_path}")

    logger.info(f"Successfully generated video: {output_path} ({output_path.stat().st_size / (1024 * 1024):.2f} MB)")
    return output_path

def cleanup_temp_video(output_path: Path) -> None:
    """Removes the generated MP4 file to reclaim disk space."""
    try:
        if output_path.exists():
            output_path.unlink()
            logger.info(f"Cleaned up temporary video: {output_path.name}")
    except Exception as e:
        logger.warning(f"Failed to remove temporary video {output_path}: {e}")
