"""ffmpeg merge engine for local app and Google Colab (no Flask)."""

from __future__ import annotations

import math
import re
import shutil
import subprocess
import uuid
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

# High-quality re-encode defaults. CRF 18 is visually transparent (near
# lossless) and the source resolution is never downscaled, so the output
# preserves the original video quality. Where the source is already an
# mp4/mov/mkv H.264/HEVC stream we skip re-encoding entirely (stream copy).
VIDEO_ENCODE = [
    "-c:v",
    "libx264",
    "-preset",
    "medium",
    "-crf",
    "18",
    "-pix_fmt",
    "yuv420p",
]
ENCODE_OPTS = [*VIDEO_ENCODE, "-c:a", "aac", "-b:a", "256k"]
AUDIO_ENCODE = ["-c:a", "aac", "-b:a", "256k"]
COPYABLE_CONTAINERS = {".mp4", ".mov", ".m4v", ".mkv"}
COPYABLE_VIDEO_CODECS = {"h264", "hevc"}
AUDIO_SAMPLE_RATE = 48000
AUDIO_CROSSFADE_MAX = 1.25
AUDIO_CROSSFADE_RATIO = 0.12
OUTPUT_END_FADE = 0.75
MAX_ACROSSFADE_COPIES = 36


def format_ffmpeg_error(stderr: str) -> str:
    if "No space left on device" in stderr:
        return "Not enough disk space. Free up space and try again."
    lines = [
        line.strip()
        for line in stderr.splitlines()
        if line.strip() and not line.strip().startswith("frame=")
    ]
    for line in reversed(lines):
        if any(
            token in line
            for token in ("Error", "error", "Invalid", "failed", "Failed")
        ):
            return line
    return lines[-1] if lines else "Video processing failed."


def run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(format_ffmpeg_error(result.stderr))


def ensure_disk_space(path: Path, target_seconds: float) -> None:
    estimated_bytes = int(target_seconds * 2.5 * 1024 * 1024) + 200 * 1024 * 1024
    free_bytes = shutil.disk_usage(path).free
    if free_bytes < estimated_bytes:
        free_gb = free_bytes / (1024**3)
        raise ValueError(
            f"Not enough disk space ({free_gb:.1f} GB free). "
            "Free up space and try again."
        )


def probe_stream_duration(path: Path, stream: str) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            stream,
            "-show_entries",
            "stream=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    value = result.stdout.strip()
    if value and value != "N/A":
        return float(value)

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def probe_image_size(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    width_str, height_str = result.stdout.strip().split(",")
    return int(width_str), int(height_str)


def still_canvas_size(image_path: Path) -> tuple[int, int]:
    width, height = probe_image_size(image_path)
    if height > width:
        return 1080, 1920
    return 1920, 1080


def still_scale_filter(canvas_w: int, canvas_h: int) -> str:
    return (
        f"scale={canvas_w}:{canvas_h}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={canvas_w}:{canvas_h}:(ow-iw)/2:(oh-ih)/2:color=black,"
        "setsar=1,format=yuv420p"
    )


def probe_has_audio(path: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def probe_video_codec(path: Path) -> str:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip().lower() if result.returncode == 0 else ""


def can_copy_video(path: Path) -> bool:
    """True when the source video can be losslessly stream-copied into MP4."""
    return (
        path.suffix.lower() in COPYABLE_CONTAINERS
        and probe_video_codec(path) in COPYABLE_VIDEO_CODECS
    )


def max_canvas_size(clip_paths: list[Path]) -> tuple[int, int]:
    """Largest width/height across clips so nothing is ever downscaled."""
    max_w = max_h = 0
    for clip in clip_paths:
        try:
            width, height = probe_image_size(clip)
        except Exception:
            continue
        max_w = max(max_w, width)
        max_h = max(max_h, height)
    if max_w <= 0 or max_h <= 0:
        return 1920, 1080
    # libx264 requires even dimensions.
    return max_w - (max_w % 2), max_h - (max_h % 2)


def audio_crossfade_seconds(clip_duration: float) -> float:
    if clip_duration < 0.5:
        return 0.0
    fade = min(AUDIO_CROSSFADE_MAX, clip_duration * AUDIO_CROSSFADE_RATIO)
    fade = min(fade, clip_duration * 0.35)
    return round(fade, 3) if fade >= 0.12 else 0.0


def output_end_fade_seconds(target_seconds: float) -> float:
    return min(OUTPUT_END_FADE, max(0.12, target_seconds * 0.08))


def copies_for_crossfade(
    clip_duration: float, fade: float, target_seconds: float
) -> int:
    step = max(clip_duration - fade, 0.05)
    return max(2, math.ceil((target_seconds - fade) / step))


def simple_audio_filter(clip_duration: float, target_seconds: float, pad: bool) -> str:
    end_at = min(clip_duration, target_seconds)
    end_fade = min(output_end_fade_seconds(target_seconds), max(0.12, end_at * 0.5))
    end_start = max(0.0, end_at - end_fade)
    parts = [
        f"[0:a:0]aresample={AUDIO_SAMPLE_RATE}",
        "aformat=sample_fmts=fltp:channel_layouts=stereo",
        "asetpts=PTS-STARTPTS",
        f"atrim=0:{target_seconds:.6f}",
        "asetpts=PTS-STARTPTS",
        f"afade=t=out:st={end_start:.6f}:d={end_fade:.6f}",
    ]
    if pad:
        parts.append(f"apad=whole_dur={target_seconds:.6f}")
    return ",".join(parts) + "[a]"


def crossfade_audio_filter(
    fade: float,
    target_seconds: float,
    copies: int,
    apply_end_fade: bool,
) -> str:
    copies = max(2, min(copies, MAX_ACROSSFADE_COPIES))
    labels = "".join(f"[s{i}]" for i in range(copies))
    inputs = "".join(f"[s{i}]" for i in range(copies))
    audio_chain = (
        f"{inputs}acrossfade=n={copies}:d={fade:.6f}:c1=hsin:c2=hsin,"
        f"atrim=0:{target_seconds:.6f},asetpts=PTS-STARTPTS,"
        f"apad=whole_dur={target_seconds:.6f}"
    )
    if apply_end_fade:
        end_fade = output_end_fade_seconds(target_seconds)
        end_start = max(0.0, target_seconds - end_fade)
        audio_chain += f",afade=t=out:st={end_start:.6f}:d={end_fade:.6f}"

    return (
        f"[0:a:0]aresample={AUDIO_SAMPLE_RATE},"
        "aformat=sample_fmts=fltp:channel_layouts=stereo,"
        "asetpts=PTS-STARTPTS[src];"
        f"[src]asplit={copies}{labels};"
        f"{audio_chain}[a]"
    )


def encode_crossfaded_audio(
    source: Path,
    dest: Path,
    fade: float,
    target_seconds: float,
    copies: int,
    apply_end_fade: bool,
) -> None:
    run_ffmpeg(
        [
            "-i",
            str(source),
            "-vn",
            "-filter_complex",
            crossfade_audio_filter(fade, target_seconds, copies, apply_end_fade),
            "-map",
            "[a]",
            "-t",
            str(target_seconds),
            *AUDIO_ENCODE,
            str(dest),
        ]
    )


def render_audio_track(
    source: Path,
    dest: Path,
    clip_duration: float,
    target_seconds: float,
    should_loop: bool,
    pad_to_target: bool = True,
) -> None:
    fade = audio_crossfade_seconds(clip_duration) if should_loop else 0.0
    needs_loop = should_loop and target_seconds > clip_duration + 0.05 and fade > 0

    if not needs_loop:
        run_ffmpeg(
            [
                "-i",
                str(source),
                "-vn",
                "-filter_complex",
                simple_audio_filter(
                    clip_duration, target_seconds, pad=pad_to_target
                ),
                "-map",
                "[a]",
                "-t",
                str(target_seconds),
                *AUDIO_ENCODE,
                str(dest),
            ]
        )
        return

    current_source = source
    current_duration = clip_duration
    current_fade = fade

    for _ in range(8):
        copies = copies_for_crossfade(
            current_duration, current_fade, target_seconds
        )
        if copies <= MAX_ACROSSFADE_COPIES:
            encode_crossfaded_audio(
                current_source,
                dest,
                current_fade,
                target_seconds,
                copies,
                apply_end_fade=True,
            )
            return

        block_duration = (
            MAX_ACROSSFADE_COPIES * current_duration
            - (MAX_ACROSSFADE_COPIES - 1) * current_fade
        )
        if block_duration <= current_duration + 0.05:
            break

        block_path = dest.with_name(f"audio-block-{uuid.uuid4().hex[:8]}.m4a")
        encode_crossfaded_audio(
            current_source,
            block_path,
            current_fade,
            block_duration,
            MAX_ACROSSFADE_COPIES,
            apply_end_fade=False,
        )
        current_source = block_path
        current_duration = probe_stream_duration(block_path, "a:0")
        current_fade = audio_crossfade_seconds(current_duration)

    encode_crossfaded_audio(
        current_source,
        dest,
        current_fade,
        target_seconds,
        MAX_ACROSSFADE_COPIES,
        apply_end_fade=True,
    )


def stream_loop_flags(_loop_count: int | None = None) -> list[str]:
    # Always loop until -t trims to the target length.
    return ["-stream_loop", "-1"]


def target_from_loop_count(
    loop_mode: str,
    loop_count: int,
    video_duration: float,
    audio_duration: float,
) -> float:
    if loop_mode == "video":
        return max(loop_count * video_duration, audio_duration)
    if loop_mode == "audio":
        return max(video_duration, loop_count * audio_duration)
    return max(loop_count * video_duration, loop_count * audio_duration)


def resolve_merge_plan(
    video_path: Path | None,
    audio_path: Path | None,
    target_seconds: float | None,
    loop_mode: str | None,
    loop_count: int | None,
) -> tuple[float, str, int | None]:
    has_video = video_path is not None
    has_audio = audio_path is not None
    video_duration = (
        probe_stream_duration(video_path, "v:0") if has_video else 0.0
    )
    audio_duration = (
        probe_stream_duration(audio_path, "a:0") if has_audio else 0.0
    )

    if has_video and has_audio:
        if loop_mode not in {"video", "audio", "both"}:
            raise ValueError("Choose whether to loop video, audio, or both.")

        if target_seconds is not None:
            return target_seconds, loop_mode, None

        if loop_count is not None:
            target = target_from_loop_count(
                loop_mode, loop_count, video_duration, audio_duration
            )
            return target, loop_mode, loop_count

        return max(video_duration, audio_duration), loop_mode, None

    mode = "video" if has_video else "audio"
    source_duration = video_duration if has_video else audio_duration

    if target_seconds is not None:
        return target_seconds, mode, None

    if loop_count is not None:
        return loop_count * source_duration, mode, loop_count

    raise ValueError(
        "Provide target duration or loop count when using only video or only audio."
    )


def mux_video_with_audio(
    video_args: list[str],
    audio_path: Path,
    output_path: Path,
    target_seconds: float,
    video_map: str = "0:v:0",
    extra_args: list[str] | None = None,
    copy_video: bool = False,
) -> None:
    video_codec = ["-c:v", "copy"] if copy_video else VIDEO_ENCODE
    run_ffmpeg(
        [
            *video_args,
            "-i",
            str(audio_path),
            "-t",
            str(target_seconds),
            "-map",
            video_map,
            "-map",
            "1:a:0",
            *(extra_args or []),
            *video_codec,
            *AUDIO_ENCODE,
            str(output_path),
        ]
    )


def build_looped_video(
    video_path: Path,
    output_path: Path,
    target_seconds: float,
    loop_count: int | None,
    work_dir: Path,
    mute: bool = False,
) -> None:
    copy_video = can_copy_video(video_path)
    video_args = [
        *stream_loop_flags(loop_count),
        "-fflags",
        "+genpts",
        "-i",
        str(video_path),
    ]
    if mute or not probe_has_audio(video_path):
        video_codec = ["-c:v", "copy"] if copy_video else VIDEO_ENCODE
        run_ffmpeg(
            [
                *video_args,
                "-t",
                str(target_seconds),
                "-an",
                *video_codec,
                str(output_path),
            ]
        )
        return

    audio_duration = probe_stream_duration(video_path, "a:0")
    processed = work_dir / "looped-audio.m4a"
    render_audio_track(
        source=video_path,
        dest=processed,
        clip_duration=audio_duration,
        target_seconds=target_seconds,
        should_loop=True,
    )
    mux_video_with_audio(
        video_args, processed, output_path, target_seconds, copy_video=copy_video
    )


def build_still_image_video(
    image_path: Path,
    output_path: Path,
    target_seconds: float,
    work_dir: Path,
    audio_path: Path | None = None,
) -> None:
    canvas_w, canvas_h = still_canvas_size(image_path)
    still_clip = work_dir / "still.mp4"
    run_ffmpeg(
        [
            "-loop",
            "1",
            "-framerate",
            "30",
            "-i",
            str(image_path),
            "-t",
            "2",
            "-vf",
            still_scale_filter(canvas_w, canvas_h),
            "-c:v",
            "libx264",
            "-tune",
            "stillimage",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-crf",
            "18",
            str(still_clip),
        ]
    )

    video_args = ["-fflags", "+genpts", "-stream_loop", "-1", "-i", str(still_clip)]
    if audio_path is None:
        run_ffmpeg(
            [
                *video_args,
                "-t",
                str(target_seconds),
                "-an",
                "-c:v",
                "copy",
                str(output_path),
            ]
        )
        return

    audio_duration = probe_stream_duration(audio_path, "a:0")
    processed = work_dir / "looped-audio.m4a"
    render_audio_track(
        source=audio_path,
        dest=processed,
        clip_duration=audio_duration,
        target_seconds=target_seconds,
        should_loop=target_seconds > audio_duration + 0.05,
    )
    run_ffmpeg(
        [
            *video_args,
            "-i",
            str(processed),
            "-t",
            str(target_seconds),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(output_path),
        ]
    )


def build_looped_audio_video(
    audio_path: Path,
    output_path: Path,
    target_seconds: float,
    loop_count: int | None,
    work_dir: Path,
) -> None:
    audio_duration = probe_stream_duration(audio_path, "a:0")
    processed = work_dir / "looped-audio.m4a"
    render_audio_track(
        source=audio_path,
        dest=processed,
        clip_duration=audio_duration,
        target_seconds=target_seconds,
        should_loop=True,
    )
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=1080x1920:r=30:d={target_seconds}",
            "-i",
            str(processed),
            "-t",
            str(target_seconds),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            *ENCODE_OPTS,
            "-shortest",
            str(output_path),
        ]
    )


def normalize_clip_for_stage(
    clip_path: Path,
    dest_path: Path,
    canvas_w: int = 1920,
    canvas_h: int = 1080,
) -> float:
    """Re-encode a clip to a shared canvas (no audio) for reliable concat."""
    vf = (
        f"scale={canvas_w}:{canvas_h}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={canvas_w}:{canvas_h}:(ow-iw)/2:(oh-ih)/2:color=black,"
        "setsar=1,fps=30,format=yuv420p"
    )
    run_ffmpeg(
        [
            "-i",
            str(clip_path),
            "-an",
            "-vf",
            vf,
            *VIDEO_ENCODE,
            str(dest_path),
        ]
    )
    return probe_stream_duration(dest_path, "v:0")


def stage_video_clips(
    clip_paths: list[Path],
    output_path: Path,
    work_dir: Path,
    keep_audio: bool = False,
) -> float:
    """Concatenate short animations in order into one staged video.

    Clips are padded to the largest source resolution (never downscaled) and
    re-encoded at high quality. When ``keep_audio`` is True each clip keeps its
    own audio (silence is synthesized for clips without one) so the staged
    sequence carries sound; otherwise the sequence is silent.
    """
    if not clip_paths:
        raise ValueError("Add at least one video clip to stage.")

    canvas_w, canvas_h = max_canvas_size(clip_paths)

    def _normalize(clip: Path, dest: Path) -> None:
        if keep_audio:
            normalize_clip_for_stitch(clip, dest, True, canvas_w, canvas_h)
        else:
            normalize_clip_for_stage(clip, dest, canvas_w, canvas_h)

    if len(clip_paths) == 1:
        _normalize(clip_paths[0], output_path)
        return probe_stream_duration(output_path, "v:0")

    normalized: list[Path] = []
    for index, clip in enumerate(clip_paths):
        dest = work_dir / f"stage-clip-{index:03d}.mp4"
        _normalize(clip, dest)
        normalized.append(dest)

    list_file = work_dir / "stage-concat.txt"
    lines = []
    for path in normalized:
        escaped = str(path.resolve()).replace("'", r"'\''")
        lines.append(f"file '{escaped}'")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(output_path),
        ]
    )
    return probe_stream_duration(output_path, "v:0")


def normalize_clip_for_stitch(
    clip_path: Path,
    dest_path: Path,
    keep_audio: bool,
    canvas_w: int = 1920,
    canvas_h: int = 1080,
) -> float:
    """Re-encode a clip to a shared video (and audio) layout for concat.

    When ``keep_audio`` is True every clip gets an AAC 48k stereo track (a
    silent one is synthesized for clips that have no audio) so the concat
    demuxer can copy streams cleanly.
    """
    vf = (
        f"scale={canvas_w}:{canvas_h}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={canvas_w}:{canvas_h}:(ow-iw)/2:(oh-ih)/2:color=black,"
        "setsar=1,fps=30,format=yuv420p"
    )
    video_codec = list(VIDEO_ENCODE)

    if not keep_audio:
        run_ffmpeg(["-i", str(clip_path), "-an", "-vf", vf, *video_codec, str(dest_path)])
        return probe_stream_duration(dest_path, "v:0")

    if probe_has_audio(clip_path):
        run_ffmpeg(
            [
                "-i",
                str(clip_path),
                "-vf",
                vf,
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                *video_codec,
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                str(AUDIO_SAMPLE_RATE),
                "-ac",
                "2",
                str(dest_path),
            ]
        )
    else:
        run_ffmpeg(
            [
                "-i",
                str(clip_path),
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=channel_layout=stereo:sample_rate={AUDIO_SAMPLE_RATE}",
                "-vf",
                vf,
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-shortest",
                *video_codec,
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(dest_path),
            ]
        )
    return probe_stream_duration(dest_path, "v:0")


def stitch_video_clips(
    clip_paths: list[Path],
    output_path: Path,
    work_dir: Path,
    keep_audio: bool,
) -> float:
    """Join clips end-to-end once (no looping). Returns the output duration."""
    if not clip_paths:
        raise ValueError("Add at least one video clip to stitch.")

    canvas_w, canvas_h = max_canvas_size(clip_paths)
    normalized: list[Path] = []
    for index, clip in enumerate(clip_paths):
        dest = work_dir / f"stitch-clip-{index:03d}.mp4"
        normalize_clip_for_stitch(clip, dest, keep_audio, canvas_w, canvas_h)
        normalized.append(dest)

    list_file = work_dir / "stitch-concat.txt"
    lines = []
    for path in normalized:
        escaped = str(path.resolve()).replace("'", r"'\''")
        lines.append(f"file '{escaped}'")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(output_path),
        ]
    )
    return probe_stream_duration(output_path, "v:0")


def resolve_staged_plan(
    sequence_duration: float,
    audio_path: Path | None,
    target_seconds: float | None,
    loop_count: int | None,
) -> tuple[float, str, int | None]:
    """Pick output length for a staged clip sequence.

    With audio and no duration/loop count: match the audio (extend/loop the
    staged video when audio is longer). With loop count: loop_count × sequence.
    """
    audio_duration = (
        probe_stream_duration(audio_path, "a:0") if audio_path is not None else 0.0
    )

    if target_seconds is not None:
        mode = "staged+audio" if audio_path is not None else "staged"
        return target_seconds, mode, None

    if loop_count is not None:
        target = loop_count * sequence_duration
        if audio_path is not None:
            target = max(target, audio_duration)
        mode = "staged+audio" if audio_path is not None else "staged"
        return target, mode, loop_count

    if audio_path is not None:
        # Fit both accurately: use the longer of sequence vs audio, looping video.
        return max(sequence_duration, audio_duration), "staged+audio", None

    return sequence_duration, "staged", None


def build_staged_video_with_audio(
    staged_video: Path,
    audio_path: Path | None,
    output_path: Path,
    target_seconds: float,
    work_dir: Path,
    mute: bool = False,
) -> None:
    """Loop the staged sequence to target_seconds; mux audio when provided."""
    if audio_path is None:
        build_looped_video(
            staged_video, output_path, target_seconds, None, work_dir, mute=mute
        )
        return

    audio_duration = probe_stream_duration(audio_path, "a:0")
    processed = work_dir / "looped-audio.m4a"
    # Extend video to audio (or target); do not loop audio unless target > audio.
    render_audio_track(
        source=audio_path,
        dest=processed,
        clip_duration=audio_duration,
        target_seconds=target_seconds,
        should_loop=target_seconds > audio_duration + 0.05,
        pad_to_target=True,
    )
    video_args = [*stream_loop_flags(None), "-i", str(staged_video)]
    mux_video_with_audio(video_args, processed, output_path, target_seconds)


def build_merged_video(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    target_seconds: float,
    loop_mode: str,
    loop_count: int | None,
    work_dir: Path,
) -> None:
    audio_duration = probe_stream_duration(audio_path, "a:0")
    processed = work_dir / "looped-audio.m4a"
    render_audio_track(
        source=audio_path,
        dest=processed,
        clip_duration=audio_duration,
        target_seconds=target_seconds,
        should_loop=loop_mode in {"audio", "both"},
        pad_to_target=True,
    )

    if loop_mode in {"video", "both"}:
        video_args = [
            *stream_loop_flags(loop_count if loop_mode in {"video", "both"} else None),
            "-i",
            str(video_path),
        ]
        mux_video_with_audio(video_args, processed, output_path, target_seconds)
        return

    video_duration = min(probe_stream_duration(video_path, "v:0"), target_seconds)
    pad_seconds = max(0.0, target_seconds - video_duration)
    if pad_seconds > 0:
        video_filter = (
            f"[0:v]trim=duration={video_duration},setpts=PTS-STARTPTS,"
            f"tpad=stop_mode=clone:stop_duration={pad_seconds}[v]"
        )
    else:
        video_filter = f"[0:v]trim=duration={target_seconds},setpts=PTS-STARTPTS[v]"

    run_ffmpeg(
        [
            "-i",
            str(video_path),
            "-i",
            str(processed),
            "-t",
            str(target_seconds),
            "-filter_complex",
            video_filter,
            "-map",
            "[v]",
            "-map",
            "1:a:0",
            *ENCODE_OPTS,
            str(output_path),
        ]
    )


def normalize_output_name(name: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", name.strip()).strip("._")
    if not cleaned:
        raise ValueError("Output filename is required.")
    if not cleaned.lower().endswith(".mp4"):
        cleaned += ".mp4"
    return cleaned


def parse_duration_minutes(raw: str | float | int | None) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        if raw <= 0:
            raise ValueError("Duration must be a positive number (minutes).")
        return float(raw) * 60
    value = str(raw).strip()
    if not value:
        return None
    minutes = float(value)
    if minutes <= 0:
        raise ValueError("Duration must be a positive number (minutes).")
    return minutes * 60


def parse_loop_count(raw: str | int | None) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, int):
        if raw < 1:
            raise ValueError("Loop count must be at least 1.")
        return raw
    value = str(raw).strip()
    if not value:
        return None
    if not value.isdigit():
        raise ValueError("Loop count must be a whole number.")
    count = int(value)
    if count < 1:
        raise ValueError("Loop count must be at least 1.")
    return count


def _optional_path(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return Path(text).expanduser()


def run_merge(
    *,
    video_path: str | Path | None = None,
    video_paths: list[str | Path] | None = None,
    image_path: str | Path | None = None,
    audio_path: str | Path | None = None,
    output_folder: str | Path,
    output_name: str,
    loop_mode: str | None = None,
    loop_count: str | int | None = None,
    duration_minutes: str | float | int | None = None,
    stitch: bool = False,
    keep_source_audio: bool = True,
    mute: bool = False,
    work_dir: str | Path | None = None,
) -> dict:
    """Merge video/image + audio and write an MP4 into output_folder.

    Pass ``video_paths`` (2+) to stage short animations in order; the staged
    sequence loops when audio (or target duration) is longer.

    Set ``stitch=True`` with 2+ ``video_paths`` to join the clips end-to-end
    once (no looping). ``keep_source_audio`` keeps each clip's own audio; when
    an ``audio_path`` is also given it becomes the soundtrack over the stitched
    video (played once, trimmed/padded to the stitched length).

    ``mute`` only applies when there is video but no external ``audio_path``:
    when True the output is silent, when False the video's own audio is kept.

    Returns a dict with path, filename, duration_seconds, loop_mode, loop_count.
    """
    clips: list[Path] = []
    if video_paths:
        for item in video_paths:
            path = _optional_path(item)
            if path is not None:
                clips.append(path)
    single = _optional_path(video_path)
    if single is not None and not clips:
        clips = [single]
    elif single is not None and clips:
        raise ValueError("Pass either video_path or video_paths, not both.")

    image = _optional_path(image_path)
    audio = _optional_path(audio_path)
    out_dir = Path(output_folder).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    has_clips = len(clips) > 0
    has_image = image is not None
    has_audio = audio is not None
    multi_stage = len(clips) > 1
    # Only relevant when there is video but no external soundtrack: decide
    # whether to keep the source video audio or produce a silent output.
    # ``keep_source_audio=False`` (legacy stitch flag) implies muting too.
    mute_source = bool(mute) or not keep_source_audio

    if has_clips and has_image:
        raise ValueError("Use either video(s) or a still image, not both.")
    if not has_clips and not has_image and not has_audio:
        raise ValueError("Add a video, staged videos, a still image, or an audio file.")

    for clip in clips:
        if not clip.exists():
            raise FileNotFoundError(f"Video not found: {clip}")
        if clip.suffix.lower() not in VIDEO_EXTENSIONS:
            raise ValueError(f"Unsupported video format: {clip.suffix}")

    if has_image:
        if not image.exists():
            raise FileNotFoundError(f"Image not found: {image}")
        if image.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError(f"Unsupported image format: {image.suffix}")

    if has_audio:
        if not audio.exists():
            raise FileNotFoundError(f"Audio not found: {audio}")
        if audio.suffix.lower() not in AUDIO_EXTENSIONS:
            raise ValueError(f"Unsupported audio format: {audio.suffix}")

    target_seconds = parse_duration_minutes(duration_minutes)
    resolved_loop_count_input = parse_loop_count(loop_count)
    output_filename = normalize_output_name(output_name)
    output_path = out_dir / output_filename
    if output_path.exists():
        raise ValueError(f"File already exists: {output_filename}")

    tmp_root = Path(work_dir) if work_dir else out_dir / ".tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    upload_dir = tmp_root / f"job-{uuid.uuid4().hex}"
    upload_dir.mkdir(parents=True, exist_ok=True)

    do_stitch = stitch and len(clips) >= 2

    try:
        if do_stitch:
            total_duration = sum(
                probe_stream_duration(clip, "v:0") for clip in clips
            )
            ensure_disk_space(out_dir, total_duration)

            if has_audio:
                stitched = upload_dir / "stitched.mp4"
                stitch_video_clips(
                    clips, stitched, upload_dir, keep_audio=False
                )
                resolved_target = probe_stream_duration(stitched, "v:0")
                audio_duration = probe_stream_duration(audio, "a:0")
                processed = upload_dir / "stitch-audio.m4a"
                render_audio_track(
                    source=audio,
                    dest=processed,
                    clip_duration=audio_duration,
                    target_seconds=resolved_target,
                    should_loop=False,
                    pad_to_target=True,
                )
                mux_video_with_audio(
                    ["-i", str(stitched)],
                    processed,
                    output_path,
                    resolved_target,
                )
                resolved_loop = "stitch+soundtrack"
                resolved_loop_count = None
            else:
                resolved_target = stitch_video_clips(
                    clips, output_path, upload_dir, keep_audio=not mute_source
                )
                resolved_loop = "stitch-silent" if mute_source else "stitch"
                resolved_loop_count = None
        elif multi_stage:
            staged = upload_dir / "staged.mp4"
            # Keep each clip's audio through staging only when there is no
            # external soundtrack and the user did not ask to mute.
            keep_staged_audio = not has_audio and not mute_source
            sequence_duration = stage_video_clips(
                clips, staged, upload_dir, keep_audio=keep_staged_audio
            )
            resolved_target, resolved_loop, resolved_loop_count = resolve_staged_plan(
                sequence_duration,
                audio if has_audio else None,
                target_seconds,
                resolved_loop_count_input,
            )
            ensure_disk_space(out_dir, resolved_target)
            build_staged_video_with_audio(
                staged_video=staged,
                audio_path=audio if has_audio else None,
                output_path=output_path,
                target_seconds=resolved_target,
                work_dir=upload_dir,
                mute=mute_source,
            )
        elif has_image:
            if has_audio:
                audio_duration = probe_stream_duration(audio, "a:0")
                if target_seconds is not None:
                    resolved_target = target_seconds
                    resolved_loop_count = None
                elif resolved_loop_count_input is not None:
                    resolved_target = resolved_loop_count_input * audio_duration
                    resolved_loop_count = resolved_loop_count_input
                else:
                    resolved_target = audio_duration
                    resolved_loop_count = None
                resolved_loop = "image+audio"
            else:
                if target_seconds is None:
                    raise ValueError(
                        "Provide target duration when using only a still image."
                    )
                resolved_target = target_seconds
                resolved_loop = "image"
                resolved_loop_count = None

            ensure_disk_space(out_dir, resolved_target)
            build_still_image_video(
                image_path=image,
                output_path=output_path,
                target_seconds=resolved_target,
                work_dir=upload_dir,
                audio_path=audio,
            )
        else:
            video = clips[0] if clips else None
            mode = (loop_mode or "").strip() or None
            if has_clips and has_audio and mode is None:
                # Single clip + audio: default to looping video to fit audio.
                mode = "video"
            resolved_target, resolved_loop, resolved_loop_count = resolve_merge_plan(
                video_path=video,
                audio_path=audio,
                target_seconds=target_seconds,
                loop_mode=mode,
                loop_count=resolved_loop_count_input,
            )
            ensure_disk_space(out_dir, resolved_target)

            if has_clips and not has_audio:
                build_looped_video(
                    video,
                    output_path,
                    resolved_target,
                    resolved_loop_count,
                    upload_dir,
                    mute=mute_source,
                )
                if mute_source:
                    resolved_loop = f"{resolved_loop}-muted"
            elif has_audio and not has_clips:
                build_looped_audio_video(
                    audio,
                    output_path,
                    resolved_target,
                    resolved_loop_count,
                    upload_dir,
                )
            else:
                build_merged_video(
                    video_path=video,
                    audio_path=audio,
                    output_path=output_path,
                    target_seconds=resolved_target,
                    loop_mode=resolved_loop,
                    loop_count=resolved_loop_count,
                    work_dir=upload_dir,
                )
    finally:
        shutil.rmtree(upload_dir, ignore_errors=True)

    return {
        "success": True,
        "path": str(output_path),
        "filename": output_filename,
        "duration_seconds": round(resolved_target, 2),
        "loop_mode": resolved_loop,
        "loop_count": resolved_loop_count,
    }
