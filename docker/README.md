# babelscribe in Docker

For servers, NAS boxes and anything else where installing Python, ffmpeg and a whisper.cpp build is a chore.

## Use it

Subtitles are written next to the input, so mount the folder that holds your media:

```bash
docker run --rm \
  -v "$PWD:/media" \
  -v babelscribe-models:/models \
  ghcr.io/phonology024/babelscribe:latest talk.mp4
```

That writes `talk.srt` and `talk.json` into the folder you ran it from.

Other languages, fewer errors, more formats — every CLI flag works:

```bash
docker run --rm -v "$PWD:/media" -v babelscribe-models:/models \
  ghcr.io/phonology024/babelscribe:latest talk.mp4 -l th --accurate -f srt,vtt,txt
```

Or drop into a shell for a batch of files:

```bash
docker run --rm -it -v "$PWD:/media" -v babelscribe-models:/models \
  --entrypoint sh ghcr.io/phonology024/babelscribe:latest
# babelscribe one.mp4 -f srt; babelscribe two.mp4 -f srt
```

## The two volumes, and why there are two

| Mount | Holds | Why mount it |
|---|---|---|
| `/models` | the speech models (1.6 GB for turbo) | otherwise every `--rm` run downloads them again |
| `/media` | your files | this is where output is written; the working directory |

`whisper-cli` itself is baked into the image, not the volume.

## GPU

The published image ships the **CPU** build: it runs anywhere, and a Vulkan build without a passed-through GPU
fails with `libvulkan.so.1: cannot open shared object file`. If you have an AMD/Intel/NVIDIA card and want it
used, build the Vulkan variant and give the container the device:

```bash
docker build --build-arg BABELSCRIBE_FLAVOR=vulkan -t babelscribe:vulkan docker
docker run --rm --device /dev/dri \
  -v "$PWD:/media" -v babelscribe-models:/models babelscribe:vulkan talk.mp4
```

`--device /dev/dri` is what makes the host GPU visible; without it the Vulkan build falls back to the CPU anyway.

## Building it yourself

```bash
docker build -t babelscribe .                                    # CPU, current PyPI version
docker build --build-arg BABELSCRIBE_VERSION=0.3.2 -t babelscribe .
```

The build downloads the `whisper-cli` release asset and fails if this platform has none, so a broken image
never reaches a user.
