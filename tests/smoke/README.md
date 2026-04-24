## Smoke Test

To ensure the [`weaver.ini.example`](../../config/weaver.ini.example) configuration is always tested with latest
definitions, the `make test-smoke` (a.k.a `docker-test`) will copy the file locally for mounting in Docker Compose.
Only the `localhost` references are replaced by `mongodb` to refer directly to the corresponding container service.

The contents of the [`tests`](./tests) directory are mounted within the container to perform additional checks.
This allows testing internal behavior of the containers without needing to expose ports or services externally,
which better simulates a production environment to evaluate how the services are expected to be configured.
