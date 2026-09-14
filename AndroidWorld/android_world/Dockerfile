# syntax=docker/dockerfile:1
# Credits to https://github.com/amrsa1/Android-Emulator-image

FROM eclipse-temurin:18-jdk


ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /
#=============================
# Install Dependencies
#=============================
SHELL ["/bin/bash", "-c"]
RUN apt update && apt install -y curl sudo wget unzip bzip2 libdrm-dev libxkbcommon-dev libgbm-dev libasound-dev libnss3 libxcursor1 libpulse-dev libxshmfence-dev xauth xvfb x11vnc fluxbox wmctrl libdbus-glib-1-2 ffmpeg

#==============================
# Android SDK ARGS
#==============================
ARG ARCH="x86_64"
ARG TARGET="google_apis"
ARG API_LEVEL="33"
ARG BUILD_TOOLS="33.0.0"
ARG ANDROID_ARCH="x86_64"
ARG ANDROID_API_LEVEL="android-${API_LEVEL}"
ARG ANDROID_APIS="${TARGET};${ARCH}"
ARG EMULATOR_PACKAGE="system-images;${ANDROID_API_LEVEL};${ANDROID_APIS}"
ARG PLATFORM_VERSION="platforms;${ANDROID_API_LEVEL}"
ARG BUILD_TOOL="build-tools;${BUILD_TOOLS}"
ARG ANDROID_CMD="commandlinetools-linux-11076708_latest.zip"
ARG ANDROID_SDK_PACKAGES="${EMULATOR_PACKAGE} ${PLATFORM_VERSION} ${BUILD_TOOL} platform-tools emulator"

#==============================
# Set JAVA_HOME - SDK
#==============================
ENV ANDROID_SDK_ROOT=/opt/android
ENV PATH="$PATH:$ANDROID_SDK_ROOT/cmdline-tools/tools:$ANDROID_SDK_ROOT/cmdline-tools/tools/bin:$ANDROID_SDK_ROOT/emulator:$ANDROID_SDK_ROOT/tools/bin:$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/build-tools/${BUILD_TOOLS}"
ENV DOCKER="true"

#============================================
# Install required Android CMD-line tools
#============================================
RUN wget https://dl.google.com/android/repository/${ANDROID_CMD} -P /tmp && \
    unzip -d $ANDROID_SDK_ROOT /tmp/$ANDROID_CMD && \
    mkdir -p $ANDROID_SDK_ROOT/cmdline-tools/tools && cd $ANDROID_SDK_ROOT/cmdline-tools &&  mv NOTICE.txt source.properties bin lib tools/  && \
    cd $ANDROID_SDK_ROOT/cmdline-tools/tools && ls

#============================================
# Install required packages using SDK manager
#============================================
RUN yes Y | sdkmanager --licenses
# Install each SDK package in its own RUN step (own Docker layer) so a
# network stall/failure on one package only requires retrying that layer
# instead of re-downloading everything.
#
# sdkmanager's own downloader has no read-timeout: if a connection stalls
# (no error, just stops transferring data) it hangs forever instead of
# failing, so a bare retry-on-failure loop never triggers. `timeout` is used
# to force-kill a stuck attempt after N seconds so the loop can retry with a
# fresh connection. The timeout is generous (well above how long the
# download should take on a decent connection) so slow-but-progressing
# downloads aren't killed prematurely; it only kicks in for genuine stalls.
RUN for i in 1 2 3 4 5; do \
      yes Y | timeout 1200 sdkmanager --verbose --no_https "platform-tools" && break; \
      echo "Attempt $i for platform-tools failed/stalled, retrying..."; sleep 20; \
    done
RUN for i in 1 2 3 4 5; do \
      yes Y | timeout 1200 sdkmanager --verbose --no_https "${BUILD_TOOL}" && break; \
      echo "Attempt $i for ${BUILD_TOOL} failed/stalled, retrying..."; sleep 20; \
    done
RUN for i in 1 2 3 4 5; do \
      yes Y | timeout 1200 sdkmanager --verbose --no_https "${PLATFORM_VERSION}" && break; \
      echo "Attempt $i for ${PLATFORM_VERSION} failed/stalled, retrying..."; sleep 20; \
    done
RUN for i in 1 2 3 4 5; do \
      yes Y | timeout 1800 sdkmanager --verbose --no_https "emulator" && break; \
      echo "Attempt $i for emulator failed/stalled, retrying..."; sleep 20; \
    done
RUN for i in 1 2 3 4 5; do \
      yes Y | timeout 2400 sdkmanager --verbose --no_https "${EMULATOR_PACKAGE}" && break; \
      echo "Attempt $i for ${EMULATOR_PACKAGE} failed/stalled, retrying..."; sleep 20; \
    done
#============================================
# Create required emulator
#============================================
ARG EMULATOR_NAME="Pixel_6_API_33"
ARG EMULATOR_DEVICE="pixel_6"
ENV EMULATOR_NAME=$EMULATOR_NAME
ENV DEVICE_NAME=$EMULATOR_DEVICE
RUN echo "no" | avdmanager --verbose create avd --force --name "${EMULATOR_NAME}" --device "${EMULATOR_DEVICE}" --package "${EMULATOR_PACKAGE}"


#====================================
# Install Python 3.11 from source
#====================================
RUN apt-get update && \
    apt-get install -y build-essential zlib1g-dev libncurses5-dev libgdbm-dev \
    libnss3-dev libssl-dev libreadline-dev libffi-dev libsqlite3-dev wget libbz2-dev && \
    wget https://mirrors.huaweicloud.com/python/3.11.3/Python-3.11.3.tgz && \
    tar -xvf Python-3.11.3.tgz && \
    cd Python-3.11.3 && \
    ./configure --enable-optimizations && \
    make -j $(nproc) && \
    make altinstall && \
    cd .. && \
    rm -rf Python-3.11.3* && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create symlinks for python3.11
RUN ln -sf /usr/local/bin/python3.11 /usr/local/bin/python3 && \
    ln -sf /usr/local/bin/python3.11 /usr/local/bin/python

# install pip
RUN apt-get update && apt-get install python3-pip -y

#====================================
# Install uv
#====================================
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ARG PATH="$PATH:/root/.local/bin"
ENV PATH="$PATH:/root/.local/bin"

#=========================
## Copying Scripts to a dedicated project dir (NOT container root)
##=========================
## Using a dedicated WORKDIR instead of "/" matters for
## `uv pip install .` below: pyproject.toml's
## [tool.setuptools.packages.find] where=["."] is resolved relative to
## this directory. If it were "/" (as it used to be), setuptools would
## recursively walk the ENTIRE container filesystem (site-packages of all
## already-installed deps, the Android SDK under /opt, apt caches, etc.)
## looking for __init__.py files, which can silently hang for a very long
## time with zero log output during the "Building android-world" step.
WORKDIR /app
COPY . /app

RUN chmod a+x docker_setup/start_emu.sh && \
    chmod a+x docker_setup/start_emu_headless.sh && \
    chmod a+x docker_setup/entrypoint.sh

#====================================
# Install dependencies
#====================================
# RUN uv pip install . --system

#====================================
## Install dependencies
##====================================
## Use a mirror (overridable via --build-arg PIP_INDEX_URL=...) and a
## persistent BuildKit cache for uv's download/wheel cache so re-builds (or
## builds after only touching source, not deps) skip re-downloading the ~150MB
## of wheels (opencv-python, numpy, pandas, grpcio, ...) from PyPI.
ARG PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
#RUN --mount=type=cache,target=/root/.cache/uv \
#    uv pip install . --system --index-url "${PIP_INDEX_URL}"
RUN uv pip install . --system --index-url "${PIP_INDEX_URL}"
#====================================
# Pre-download app APKs at build time
#====================================
# Seed the local cache (see apps.download_app_data) with the APKs already
# checked into docker_setup/app_data/, so prefetch_apps.py below finds them
# already present and skips the network download entirely. Any app not
# present locally (e.g. newly added to apps.py) still falls back to
# downloading from GCS.
RUN mkdir -p /tmp/android_world/app_data && \
    if compgen -G "docker_setup/app_data/*.apk" > /dev/null; then \
      cp docker_setup/app_data/*.apk /tmp/android_world/app_data/; \
    fi

# Downloads every APK used by android_world's device setup into the local
# cache directory (see apps.download_app_data) so that a run-time network
# blip doesn't break container startup.
RUN python3 docker_setup/prefetch_apps.py

#=======================
# framework entry point
#=======================
ENTRYPOINT [ "./docker_setup/entrypoint.sh" ]
