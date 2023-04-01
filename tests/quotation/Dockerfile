FROM bash:latest
COPY mock_quotation_estimator.sh /bin/entrypoint

RUN chmod 755 /bin/entrypoint && \
    apk add yq

ENTRYPOINT ["bash", "/bin/entrypoint"]
