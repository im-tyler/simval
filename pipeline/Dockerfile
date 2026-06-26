FROM gromacs/gromacs:2023.2

WORKDIR /work
COPY --chown=1000:1000 1AKI.pdb minim.mdp nvt.mdp run.sh /work/
RUN chmod +x /work/run.sh && \
    useradd -m -u 1000 simval && \
    chown -R 1000:1000 /work
USER 1000

ENTRYPOINT ["/work/run.sh", "/out"]

# Build:  docker build -t simval/gromacs-lysozyme pipeline
# Run:    docker run --rm --network=none --read-only --tmpfs /tmp \
#           -v "$PWD/out":/out simval/gromacs-lysozyme
# Notes:  --network=none --read-only enforce the A7 security boundary (no
#         egress, immutable fs). Digest-pin the base in production. arm64
#         hosts need an arm64 gromacs base or emulation.
