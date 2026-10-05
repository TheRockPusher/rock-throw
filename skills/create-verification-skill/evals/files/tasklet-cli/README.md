# Tasklet

Tasklet is a small personal task-list CLI with due dates, completed tasks, and an
interactive shell. It uses Python's standard library and saves tasks as JSON.

## Development

Requires Python 3.11 or newer; there are no dependencies to install. Start with:

```sh
python3 tasklet.py --help
```

Examples:

```sh
python3 tasklet.py add "Buy groceries" --due 2026-10-12
python3 tasklet.py add "Call the dentist"
python3 tasklet.py list
python3 tasklet.py done 1
python3 tasklet.py list --all
python3 tasklet.py list --all --json
python3 tasklet.py rm 2
python3 tasklet.py --version
python3 tasklet.py shell
```

In the shell, use `add <text>`, `list`, `done <id>`, `help`, and `quit`.
End-of-file also exits. Completed tasks appear dim when listing all tasks in a
terminal; redirected output contains no colour escapes.

Data lives in `~/.tasklet/tasks.json` unless `TASKLET_HOME` is set, in which case
it lives in `$TASKLET_HOME/tasks.json`. The directory is created on the first
write, and saves replace the JSON file atomically. Task IDs are never reused
after removal.
