"""A small personal task list with a command line and an interactive shell."""

import argparse
import datetime
import json
import os
from pathlib import Path
import sys
import tempfile


VERSION = "tasklet 0.9.2"


class TaskletError(Exception):
    """An operation the user can correct."""


class TaskStore:
    def __init__(self):
        home = os.environ.get("TASKLET_HOME")
        self.path = Path(home if home is not None else os.path.expanduser("~/.tasklet")) / "tasks.json"
        self.tasks = []
        self.next_id = 1
        if self.path.exists():
            with self.path.open(encoding="utf-8") as source:
                data = json.load(source)
            self.tasks = data["tasks"]
            self.next_id = data["next_id"]

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".tasks-", suffix=".tmp", delete=False,
            ) as target:
                temporary = target.name
                json.dump({"next_id": self.next_id, "tasks": self.tasks}, target,
                          ensure_ascii=False, indent=2)
                target.write("\n")
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.path)
            temporary = None
        finally:
            if temporary is not None:
                os.unlink(temporary)

    def add(self, text, due=None):
        text = text.strip()
        if not text:
            raise TaskletError("task text cannot be empty")
        task = {"id": self.next_id, "text": text, "done": False, "due": due}
        self.tasks.append(task)
        self.next_id += 1
        self.save()
        print(f"Added #{task['id']}: {task['text']}")

    def find(self, task_id):
        for task in self.tasks:
            if task["id"] == task_id:
                return task
        raise TaskletError(f"no task #{task_id}")

    def complete(self, task_id):
        task = self.find(task_id)
        task["done"] = True
        self.save()
        print(f"Completed #{task_id}")

    def remove(self, task_id):
        task = self.find(task_id)
        self.tasks.remove(task)
        self.save()
        print(f"Removed #{task_id}")

    def show(self, include_done=False, as_json=False):
        tasks = [task for task in self.tasks if include_done or not task["done"]]
        if as_json:
            print(json.dumps(tasks, ensure_ascii=False, indent=2))
            return
        colour = sys.stdout.isatty()
        for task in tasks:
            mark = "x" if task["done"] else " "
            line = f"#{task['id']} [{mark}] {task['text']}"
            if task["due"]:
                line += f" (due {task['due']})"
            if colour and task["done"]:
                line = f"\033[2m{line}\033[0m"
            print(line)


def due_date(value):
    try:
        parsed = datetime.date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid due date {value!r}: expected YYYY-MM-DD"
        ) from None
    return value


def create_parser():
    parser = argparse.ArgumentParser(description="Keep a personal task list.")
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="add a new task")
    add.add_argument("text", metavar="TEXT")
    add.add_argument("--due", type=due_date, metavar="YYYY-MM-DD")

    listing = commands.add_parser("list", help="show open tasks")
    listing.add_argument("--all", action="store_true", help="include completed tasks")
    listing.add_argument("--json", action="store_true", help="print a JSON array")

    complete = commands.add_parser("done", help="complete a task")
    complete.add_argument("id", type=int, metavar="ID")
    remove = commands.add_parser("rm", help="remove a task")
    remove.add_argument("id", type=int, metavar="ID")
    commands.add_parser("shell", help="start an interactive task list")
    return parser


def shell():
    print(f"{VERSION} interactive - type help")
    while True:
        try:
            line = input("tasklet> ").strip()
        except EOFError:
            print()
            return
        except KeyboardInterrupt:
            print()
            return
        if not line:
            continue
        parts = line.split(maxsplit=1)
        command = parts[0]
        argument = parts[1] if len(parts) == 2 else ""
        if command == "quit" and not argument:
            return
        if command == "help" and not argument:
            print("add <text>   Add a task")
            print("list         Show open tasks")
            print("done <id>    Complete a task")
            print("help         Show these commands")
            print("quit         Exit the shell")
            continue
        try:
            # Reload for each command so CLI changes appear in a running shell.
            store = TaskStore()
            if command == "add":
                store.add(argument)
            elif command == "list" and not argument:
                store.show()
            elif command == "done":
                try:
                    task_id = int(argument)
                except ValueError:
                    raise TaskletError("done requires an integer task id") from None
                store.complete(task_id)
            else:
                raise TaskletError("unknown command; type help")
        except (TaskletError, OSError, ValueError, KeyError, TypeError) as error:
            print(f"error: {error}", file=sys.stderr)


def main():
    args = create_parser().parse_args()
    try:
        if args.command == "shell":
            shell()
            return 0
        store = TaskStore()
        if args.command == "add":
            store.add(args.text, args.due)
        elif args.command == "list":
            store.show(args.all, args.json)
        elif args.command == "done":
            store.complete(args.id)
        elif args.command == "rm":
            store.remove(args.id)
    except (TaskletError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
