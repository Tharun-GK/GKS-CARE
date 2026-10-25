import json
import re
import sys
from getpass import getpass

from werkzeug.security import generate_password_hash


USERNAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}\Z")


def main():
    users = {}
    while True:
        sys.stderr.write("Username (blank to finish): ")
        sys.stderr.flush()
        username = sys.stdin.readline().strip()
        if not username:
            break
        if not USERNAME_PATTERN.fullmatch(username) or username in users:
            raise ValueError("Username is invalid or already configured.")

        password = getpass("Password (minimum 12 characters): ")
        confirmation = getpass("Confirm password: ")
        if len(password) < 12 or password != confirmation:
            raise ValueError("Passwords must match and be at least 12 characters long.")
        users[username] = generate_password_hash(password)

    if not users:
        raise ValueError("Configure at least one account.")
    print(json.dumps(users, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
