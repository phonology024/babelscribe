# babelscribe in Docker

For servers, NAS boxes and anything else where installing Python, ffmpeg and a whisper.cpp build is a chore.

## Build it

There is no published image for 0.4.0 or earlier, so build it from a checkout (about a minute):

```bash
git clone https://github.com/phonology024/babelscribe && cd babelscribe
docker build -t babelscribe -f docker/Dockerfile .
```

The image is built from the checkout itself, so it is the version you cloned. The build downloads the
`whisper-cli` release asset and fails if this platform has none, so a broken image never gets built.
linux/amd64 only: no `linux-arm64` whisper-cli is published yet.

From the first version tag after 0.4.0, `.github/workflows/docker.yml` builds the same image, checks that it
transcribes a file, and pushes it to `ghcr.io/phonology024/babelscribe:<version>`. Until that has run once, the
`docker run` lines below only work with the image you built.

## Use it

Subtitles are written next to the input, so mount the folder that holds your media:

```bash
docker run --rm \
  -v "$PWD:/media" \
  -v babelscribe-models:/models \
  babelscribe talk.mp4
```

That writes `talk.srt` and `talk.json` into the folder you ran it from.

Other languages, fewer errors, more formats — every CLI flag works:

```bash
docker run --rm -v "$PWD:/media" -v babelscribe-models:/models \
  babelscribe talk.mp4 -l th --accurate -f srt,vtt,txt
```

Or drop into a shell for a batch of files:

```bash
docker run --rm -it -v "$PWD:/media" -v babelscribe-models:/models --entrypoint sh babelscribe
# babelscribe one.mp4 -f srt; babelscribe two.mp4 -f srt
```

## The two volumes, and why there are two

| Mount | Holds | Why mount it |
|---|---|---|
| `/models` | the speech models (1.6 GB for turbo) | otherwise every `--rm` run downloads them again |
| `/media` | your files | this is where output is written; the working directory |

`whisper-cli` itself is baked into the image, not the volume.

## GPU

The default build is **CPU**: it runs anywhere, and a Vulkan build without a passed-through GPU fails with
`libvulkan.so.1: cannot open shared object file`. If you have an AMD/Intel/NVIDIA card and want it used, build
the Vulkan variant and give the container the device:

```bash
docker build --build-arg BABELSCRIBE_FLAVOR=vulkan -t babelscribe:vulkan -f docker/Dockerfile .
docker run --rm --device /dev/dri \
  -v "$PWD:/media" -v babelscribe-models:/models babelscribe:vulkan talk.mp4
```

`--device /dev/dri` is what makes the host GPU visible. The Vulkan variant has only been checked to start
(`whisper-cli --help` loads); nobody has measured it on a GPU inside a container yet.
