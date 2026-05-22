# syntax=docker/dockerfile:1.6
#
# Debian base instead of python:3.11-slim so we can install PyQt5 from apt
# (python3-pyqt5). PyQt5 on PyPI does not ship an aarch64 wheel, and building
# it from source would require a full Qt5 dev toolchain.  The distro package
# lands in /usr/lib/python3/dist-packages and is picked up by a venv created
# with --system-site-packages.
FROM debian:bookworm-slim

ARG TARGETARCH

# ----------------------------------------------------------------------------
# System packages
#   Build:         build-essential cmake gfortran make tar
#   gs2/panjep rt: libgomp1 libgfortran5
#   Aligners:      mmseqs2 (protein), ncbi-blast+ (nucleotide: blastn/makeblastdb)
#   Python:        python3 python3-venv python3-pip  (bookworm = Python 3.11)
#   ete3 render:   python3-pyqt5 + fonts (used headless via QT_QPA_PLATFORM)
# ----------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential gfortran make tar \
      libgomp1 libgfortran5 \
      liblapacke-dev libopenblas-dev \
      mmseqs2 ncbi-blast+ \
      python3 python3-venv python3-pip \
      python3-pyqt5 python3-pyqt5.qtsvg python3-pyqt5.qtopengl \
      fontconfig fonts-dejavu-core \
      bash ca-certificates git \
 && rm -rf /var/lib/apt/lists/* \
 # gs2 uses bash extensions (e.g. `&> /dev/null`) in system() calls; point
 # /bin/sh at bash so those don't leak raw output into the program's stdout.
 && ln -sf /bin/bash /bin/sh

ENV QT_QPA_PLATFORM=offscreen \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# venv that inherits system site-packages so PyQt5 (from apt) is visible.
RUN python3 -m venv --system-site-packages /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

# ----------------------------------------------------------------------------
# Python dependencies. Installed into the venv, not system-wide (PEP 668).
# ----------------------------------------------------------------------------
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install -r requirements.txt gunicorn

# ----------------------------------------------------------------------------
# Build gs2 (LAPACK + gs2). Source is fetched from
# https://github.com/MotomuMatsui/gs at build time. Drop the bundled MMseqs2
# build step: the tarball in gs/ rejects non-SSE4.2 hosts at cmake time, and
# the distro package (mmseqs2 from apt, landing in /usr/bin/mmseqs) gives us a
# working mmseqs on both amd64 and arm64.
# ----------------------------------------------------------------------------
RUN set -eux; \
    git clone --depth 1 https://github.com/MotomuMatsui/gs.git /app/gs; \
    cd /app/gs; \
    make

# ----------------------------------------------------------------------------
# Build panjep (simple C++ build, OpenMP via libgomp). Source from
# https://github.com/MotomuMatsui/panjep.
# panjep's Makefile checks $(ARCH) against 'arm64' but uname -m returns
# 'aarch64' on Linux/aarch64, so the arm64 code path (which needs
# -flax-vector-conversions for NEON intrinsics) is skipped. Override
# explicitly when building for arm64.
# ----------------------------------------------------------------------------
RUN set -eux; \
    git clone --depth 1 https://github.com/MotomuMatsui/panjep.git /app/panjep; \
    cd /app/panjep; \
    if [ "${TARGETARCH}" = "arm64" ]; then \
        make ARCH=arm64; \
    else \
        make; \
    fi

# ----------------------------------------------------------------------------
# Build sj (hybrid GS + panjep). Source from
# https://github.com/MotomuMatsui/sj. liblapacke-dev/libopenblas-dev are
# installed up-front (see main apt step) because gs2 also needs -lopenblas at
# link time.
# ----------------------------------------------------------------------------
RUN set -eux; \
    git clone --depth 1 https://github.com/MotomuMatsui/sj.git /app/sj; \
    cd /app/sj; \
    make clean || true; \
    make

# mmseqs (from apt's mmseqs2 package) is already on PATH at /usr/bin/mmseqs.

# ----------------------------------------------------------------------------
# Application code (changes often — last for maximum cache reuse).
# ----------------------------------------------------------------------------
COPY app.py tools.py viz.py ./
COPY templates/ ./templates/
COPY static/ ./static/

EXPOSE 8000

CMD ["gunicorn", \
     "--workers", "2", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "600", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]
