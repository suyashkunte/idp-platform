# minimal-service

A conformance fixture for the platform (IDP-19). It is **not a product and not a template**: it is the smallest
service that passes `idp validate` and `make verify` with the `python-uv` build profile defaults, so platform changes
that would break tenants fail in platform CI first.

What it contains:

- `app.py`: a standard-library `http.server` app. `GET /healthz/live`, `/healthz/ready` and `/healthz/startup`
  return `200` with `{"status": "ok"}`; every other path returns `404`. Host from `HOST` (default `127.0.0.1`), port
  from `PORT` (default `8000`).
- `idp.yaml`: the service contract (`idp-service.v1`), declaring the same health paths and port.
- `Makefile`: includes the profile defaults and defines `lint`, `test`, `test-component`, `verify` and `spec-trace`.
- `tests/test_app.py`: unit tests that start the server on a free local port.

Python >= 3.9, standard library only; no `pyproject.toml` or `uv.lock` of its own.

## Running it

Inside this directory:

```sh
idp validate && make verify
```

At the platform root, `make conformance` (`idp conformance examples`) runs both for every example.

`IDP_PROFILE_DIR` defaults to `../../build-profiles/python-uv` (the profile inside this checkout). Override it to use
another copy, for example `make verify IDP_PROFILE_DIR=/path/to/build-profiles/python-uv`.

Do not run `make sbom` or `make sca` here: the example has no lockfile of its own, so the profile defaults would find
the platform workspace above and describe the platform's dependencies, not this example's.

Run `python3 app.py` to serve it by hand.
