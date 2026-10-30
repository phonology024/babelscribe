# babelscribe in a container: whisper.cpp, ffmpeg and the speech model, no host setup.
#
#   docker build -t babelscribe .
#   docker run --rm -v "$PWD:/media" -v babelscribe-models:/models babelscribe talk.mp4
#
# The binary is baked in; the model (~1.6 GB) is downloaded on first run into the /models volume, so it
# survives `docker run --rm` and is shared between files.
FROM python:3.11-slim

# libgomp1 is needed by whisper-cli's CPU path (OpenMP); ca-certificates for the model download; unzip for the
# whisper-cli release asset.
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends libgomp1 ca-certificates unzip \
 && rm -rf /var/lib/apt/lists/*

# Pinned: the image is a released artefact, so it should not follow PyPI. The CI workflow passes the version
# from pyproject.toml so a tag always builds the matching release.
ARG BABELSCRIBE_VERSION=0.3.2
RUN pip install --no-cache-dir "babelscribe==${BABELSCRIBE_VERSION}"

# Default CPU: it runs anywhere, and a Vulkan build without a passed-through GPU cannot load libvulkan.so.1.
# For a GPU host see docker/README.md.
ARG BABELSCRIBE_FLAVOR=cpu

# The Vulkan build links against the Vulkan loader, which python:3.11-slim does not ship. Installing it here
# means a --build-arg BABELSCRIBE_FLAVOR=vulkan image actually starts instead of failing at exec time.
RUN if [ "$BABELSCRIBE_FLAVOR" = "vulkan" ]; then \
      apt-get update -qq && apt-get install -y -qq --no-install-recommends libvulkan1 \
      && rm -rf /var/lib/apt/lists/*; \
    fi

# Two different homes on purpose. Setting both to /models would let an empty named volume hide the baked
# binary, and every run would download whisper-cli again.
ENV BABELSCRIBE_HOME=/opt/babelscribe \
    BABELSCRIBE_MODELS=/models

# Bake whisper-cli in, and fail the build rather than the first run if this platform has no prebuilt binary.
RUN python -c "from babelscribe import backend; backend.find_binary(flavor='${BABELSCRIBE_FLAVOR}')"

VOLUME ["/models"]
WORKDIR /media

# babelscribe writes <name>.srt next to the input, so /media must be the mounted folder.
ENTRYPOINT ["babelscribe"]
CMD ["--help"]