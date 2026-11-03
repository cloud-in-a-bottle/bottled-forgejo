# Forgejo, pinned to an exact release and its multi-arch index digest. Bump
# both together, deliberately, after CI passes.
FROM codeberg.org/forgejo/forgejo:17.0.1@sha256:fcd19ff4ebc85fb098a67e8e1d0d5a84d07dd6e8a23edcfdfd5b71a6178953be

# Runtime additions on top of the upstream Forgejo image:
#
#   python3  — runtime for the auth-proxy sidecar (auth_proxy.py);
#              uses only stdlib modules (http.client, http.server)
#   bash     — start.sh uses `wait -n`, which is bash-only
#              (busybox ash, Alpine's default /bin/sh, lacks it)
RUN apk add --no-cache python3 bash

# Copy our startup wrapper and the auth proxy.
COPY start.sh /app/start.sh
COPY auth_proxy.py /app/auth_proxy.py
RUN chmod +x /app/start.sh

EXPOSE 3000

ENTRYPOINT []
CMD ["/app/start.sh"]
