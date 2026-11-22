FROM debian:bookworm-slim

# A release moves both pins together with the version in the URL's directory and in the tar member.
ARG BITCOIN_TARBALL=bitcoin-32.1-x86_64-linux-gnu.tar.gz
ARG BITCOIN_SHA256=61545c17c3120fb7412f896d248b11993af04ec8817aad3649c55b2afb044963

# `&&` throughout, never `;`: the shell form runs `/bin/sh -c` without `-e`, so a `;` would extract a tarball whose check failed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && cd /tmp \
    && curl -fsSL -o "${BITCOIN_TARBALL}" "https://bitcoincore.org/bin/bitcoin-core-32.1/${BITCOIN_TARBALL}" \
    && echo "${BITCOIN_SHA256}  ${BITCOIN_TARBALL}" | sha256sum -c - \
    && tar -xzf "${BITCOIN_TARBALL}" -C /usr/local/bin --strip-components=2 bitcoin-32.1/bin/bitcoind \
    && rm "${BITCOIN_TARBALL}"

ENTRYPOINT ["bitcoind"]
