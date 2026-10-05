# Notes

Notes is a small personal notebook with a server-rendered web interface for creating, searching, reading, and deleting notes. Notes are stored in SQLite, and a read-only JSON API is available at `/api/notes`; `/healthz` reports the service version. The application uses only the Python standard library and requires Python 3.11 or newer.

## Development

Start the application from this directory:

```sh
python3 app.py
```

The server binds to `127.0.0.1` and defaults to port 8000. Stop it with Ctrl+C.

| Environment variable | Default | Description |
| --- | --- | --- |
| `PORT` | `8000` | HTTP port to listen on. |
| `NOTES_DB` | `notes.db` | SQLite database file path, relative to the current working directory unless absolute. |

By default, `notes.db` is created next to where you run the command. Notes persist across server restarts.
