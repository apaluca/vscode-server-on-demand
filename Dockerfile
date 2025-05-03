FROM ubuntu:24.04

RUN apt-get update && export DEBIAN_FRONTEND=noninteractive && apt-get install -y --no-install-recommends \
  # tools & required packages
  git curl wget ca-certificates \
  # clean up
  && apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

ARG VERSION="1.97.2"

# install visual studio code
RUN <<EOF
  ARCH="$(dpkg --print-architecture)";

  echo "ARCH: $ARCH";

  case "$ARCH" in
    amd64) export TARGET='cli-linux-x64' ;;
    arm64) export TARGET='cli-linux-arm64' ;;
  esac;

  wget -qO- https://update.code.visualstudio.com/${VERSION}/${TARGET}/stable | tar xvz -C /usr/bin/
  chmod +x /usr/bin/code
EOF

# entrypoint
ENTRYPOINT [ "code", "serve-web", "--without-connection-token", "--accept-server-license-terms" ]

# default arguments
CMD [ "--host", "0.0.0.0", "--port", "8000", "--cli-data-dir", "/root/.vscode/cli-data", "--user-data-dir", "/root/.vscode/user-data", "--server-data-dir", "/root/.vscode/server-data", "--extensions-dir", "/root/.vscode/extensions" ]

HEALTHCHECK NONE

# expose port
EXPOSE 8000