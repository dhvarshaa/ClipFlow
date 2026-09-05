import math
import re
import shutil
import subprocess
import uuid
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

ENCODE_OPTS = [
    "-c:v",
    "libx264",
    "-pix_fmt",
    "yuv420p",
    "-preset",
    "veryfast",
    "-c:a",
    "aac",
    "-b:a",
    "192k",
]
AUDIO_ENCODE = ["-c:a", "aac", "-b:a", "192k"]
AUDIO_SAMPLE_RATE = 48000
# Overlap used to blend the end of one loop into the start of the next.
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
    # Always loop until -t trims to the target length. A finite ffmpeg loop
    # count would stop the short video early when audio is much longer.
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
) -> None:
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
            *ENCODE_OPTS,
            str(output_path),
        ]
    )


def build_looped_video(
    video_path: Path,
    output_path: Path,
    target_seconds: float,
    loop_count: int | None,
    work_dir: Path,
) -> None:
    video_args = [
        *stream_loop_flags(loop_count),
        "-i",
        str(video_path),
    ]
    if not probe_has_audio(video_path):
        run_ffmpeg(
            [
                *video_args,
                "-t",
                str(target_seconds),
                "-an",
                *ENCODE_OPTS[:6],
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
    mux_video_with_audio(video_args, processed, output_path, target_seconds)


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
            "veryfast",
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
    cleaned = re.sub(r"[^\w.\-]+", "_", name.strip(), flags=re.ASCII)
    cleaned = cleaned.strip("._") or ""
    if not cleaned:
        raise ValueError("Output filename is required.")
    if not cleaned.lower().endswith(".mp4"):
        cleaned += ".mp4"
    return cleaned


def parse_duration_minutes(value: float | int | str | None) -> float | None:
    if value is None or value == "":
        return None
    minutes = float(value)
    if minutes <= 0:
        raise ValueError("Duration must be a positive number (minutes).")
    return minutes * 60


def parse_loop_count(value: int | str | None) -> int | None:
    if value is None or value == "":
        return None
    count = int(value)
    if count < 1:
        raise ValueError("Loop count must be at least 1.")
    return count


def _optional_path(path: str | Path | None) -> Path | None:
    if path is None:
        return None
    text = str(path).strip()
    if not text:
        return None
    return Path(text).expanduser()


def _copy_into_work(source: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return dest


def run_job(
    *,
    output_path: str | Path,
    work_dir: str | Path,
    video_path: str | Path | None = None,
    audio_path: str | Path | None = None,
    image_path: str | Path | None = None,
    duration_minutes: float | int | str | None = None,
    loop_count: int | str | None = None,
    loop_mode: str | None = None,
    overwrite: bool = False,
) -> dict:
    video_src = _optional_path(video_path)
    audio_src = _optional_path(audio_path)
    image_src = _optional_path(image_path)
    output = Path(output_path).expanduser()
    work = Path(work_dir).expanduser()
    work.mkdir(parents=True, exist_ok=True)

    has_video = video_src is not None
    has_image = image_src is not None
    has_audio = audio_src is not None

    if has_video and has_image:
        raise ValueError("Use either a video or a still image, not both.")
    if not has_video and not has_image and not has_audio:
        raise ValueError("Add a video, a still image, or an audio file.")

    if has_video and not video_src.exists():
        raise ValueError(f"Video not found: {video_src}")
    if has_image and not image_src.exists():
        raise ValueError(f"Image not found: {image_src}")
    if has_audio and not audio_src.exists():
        raise ValueError(f"Audio not found: {audio_src}")

    if has_video:
        video_ext = video_src.suffix.lower()
        if video_ext not in VIDEO_EXTENSIONS:
            raise ValueError(f"Unsupported video format: {video_ext}")
    if has_image:
        image_ext = image_src.suffix.lower()
        if image_ext not in IMAGE_EXTENSIONS:
            raise ValueError(f"Unsupported image format: {image_ext}")
    if has_audio:
        audio_ext = audio_src.suffix.lower()
        if audio_ext not in AUDIO_EXTENSIONS:
            raise ValueError(f"Unsupported audio format: {audio_ext}")

    target_seconds = parse_duration_minutes(
        None if duration_minutes in (0, 0.0, "0") else duration_minutes
    )
    count = parse_loop_count(None if loop_count in (0, "0") else loop_count)
    mode = (loop_mode or "").strip() or None
    output_filename = normalize_output_name(output.name)
    output = output.with_name(output_filename)
    output.parent.mkdir(parents=True, exist_ok=True)

    if output.exists() and not overwrite:
        raise ValueError(f"File already exists: {output}")

    local_video = None
    local_image = None
    local_audio = None
    if has_video:
        local_video = _copy_into_work(video_src, work / f"video{video_ext}")
    if has_image:
        local_image = _copy_into_work(image_src, work / f"image{image_ext}")
    if has_audio:
        local_audio = _copy_into_work(audio_src, work / f"audio{audio_ext}")

    local_output = work / output_filename

    if has_image:
        if has_audio:
            audio_duration = probe_stream_duration(local_audio, "a:0")
            if target_seconds is not None:
                resolved_target = target_seconds
                resolved_loop_count = None
            elif count is not None:
                resolved_target = count * audio_duration
                resolved_loop_count = count
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

        ensure_disk_space(work, resolved_target)
        build_still_image_video(
            image_path=local_image,
            output_path=local_output,
            target_seconds=resolved_target,
            work_dir=work,
            audio_path=local_audio,
        )
    else:
        resolved_target, resolved_loop, resolved_loop_count = resolve_merge_plan(
            video_path=local_video,
            audio_path=local_audio,
            target_seconds=target_seconds,
            loop_mode=mode,
            loop_count=count,
        )
        ensure_disk_space(work, resolved_target)
        if has_video and not has_audio:
            build_looped_video(
                local_video,
                local_output,
                resolved_target,
                resolved_loop_count,
                work,
            )
        elif has_audio and not has_video:
            build_looped_audio_video(
                local_audio,
                local_output,
                resolved_target,
                resolved_loop_count,
                work,
            )
        else:
            build_merged_video(
                video_path=local_video,
                audio_path=local_audio,
                output_path=local_output,
                target_seconds=resolved_target,
                loop_mode=resolved_loop,
                loop_count=resolved_loop_count,
                work_dir=work,
            )

    if output.resolve() != local_output.resolve():
        shutil.copy2(local_output, output)

    return {
        "success": True,
        "path": str(output),
        "filename": output_filename,
        "duration_seconds": round(resolved_target, 2),
        "loop_mode": resolved_loop,
        "loop_count": resolved_loop_count,
    }
