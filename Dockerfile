FROM docker.io/fnndsc/pl-lgd-hemis:base-1

LABEL org.opencontainers.image.authors="FNNDSC <dev@babyMRI.org>" \
      org.opencontainers.image.title="LGD WM Hemispheres" \
      org.opencontainers.image.description="White-matter hemisphere extraction for the LGD project"

WORKDIR /usr/local/src/pl-lgd-hemis

COPY . .
ARG extras_require=none
RUN pip install ".[${extras_require}]"

CMD ["lgd_hemis"]
