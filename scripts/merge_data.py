"""Safely save the bot's data files when another run changed them at the same time.

Usage: python scripts/merge_data.py <base-commit> <dir-with-this-run's-files>

The repo must already be reset to the latest remote commit. For every file this run changed:
  - history*.json / memory*.json : 3-way merge (entries added by this run are appended to the latest remote file,
                                   so nothing another run saved is lost)
  - topics*.txt                  : the latest remote file minus the lines this run used up
  - everything else              : this run's version
Files this run did not change keep the remote version.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def at_base(base, rel):
    r = subprocess.run(["git", "show", f"{base}:{rel}"], cwd=ROOT, capture_output=True)
    return r.stdout.decode("utf-8") if r.returncode == 0 else None


def merge(orig, mine, remote):
    if mine == orig:
        return remote
    if remote == orig:
        return mine
    if isinstance(mine, dict) and isinstance(remote, dict):
        orig = orig if isinstance(orig, dict) else {}
        out = dict(remote)
        for k, v in mine.items():
            out[k] = merge(orig.get(k), v, remote[k]) if k in remote else v
        return out
    if isinstance(mine, list) and isinstance(remote, list):
        orig = orig if isinstance(orig, list) else []
        new = [x for x in mine if x not in orig]
        return remote + [x for x in new if x not in remote]
    return mine


def main():
    base, mine_dir = sys.argv[1], Path(sys.argv[2])
    for p in sorted(mine_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(mine_dir).as_posix()
        if p.suffix.lower() not in (".json", ".txt", ".log", ".md", ".yaml", ".yml", ".csv"):
            dest = ROOT / rel                  # binary files (thumbnails...): this run's copy wins
            if not dest.exists() or dest.read_bytes() != p.read_bytes():
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(p.read_bytes())
            continue
        mine = p.read_text(encoding="utf-8")
        orig = at_base(base, rel)
        dest = ROOT / rel
        remote = dest.read_text(encoding="utf-8") if dest.exists() else None
        if mine == orig:
            continue                       # this run did not touch it
        name = Path(rel).name
        out = mine
        if remote is not None and orig is not None and remote != orig:
            if name.endswith(".json") and name.startswith(("history", "memory")):
                try:
                    out = json.dumps(merge(json.loads(orig), json.loads(mine), json.loads(remote)),
                                     ensure_ascii=False, indent=1)
                    print("merged", rel)
                except ValueError:
                    out = mine
            elif name.startswith("topics") and name.endswith(".txt"):
                mine_lines = set(mine.splitlines())
                used = {ln for ln in orig.splitlines() if ln.strip() and ln not in mine_lines}
                out = "\n".join(ln for ln in remote.splitlines() if ln not in used) + "\n"
                print("merged", rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
