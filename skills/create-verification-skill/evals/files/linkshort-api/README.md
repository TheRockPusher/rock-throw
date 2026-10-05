# Linkshort API

A small JSON URL-shortening service with persistent links and click counts. Link codes are six-character base62 strings. Linkshort uses Python's threaded HTTP server and stores its data in an atomically replaced JSON file.

The API supports creating and listing links at `/api/links`, redirecting through `/<code>`, retrieving statistics at `/api/links/<code>/stats`, and deleting links at `/api/links/<code>`. The health endpoint is `/api/health`.

## Development

Requires Python 3.11 or newer; no third-party dependencies are needed.

The admin UI in `static/` is built and copied from the separate `linkshort-admin` repo. The service mounts it at `/admin/` and requires that directory at startup.

```sh
python3 server.py
```

Configuration is read from the environment:

- `LINKSHORT_PORT`: listening port, default `8080`. The server binds to `127.0.0.1` only.
- `LINKSHORT_DATA`: JSON data file, default `links.json` in the current working directory. Relative paths are resolved from that directory.

Stop the foreground service with Ctrl-C. Saved links and click counts survive restarts.
