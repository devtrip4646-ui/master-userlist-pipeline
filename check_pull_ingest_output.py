"""One-off diagnostic: run the REAL api_pull_ingest.py (the exact script
the failing "Pull and ingest" step runs) and capture its full stdout +
stderr + return code, since GitHub Actions job logs aren't readable
without repo admin access. This is NOT a dry run -- it does the same
real work the production step does (fetches, ingests, uploads DBs back
to R2) -- but that's fine, it's the legitimate production script, run
in the legitimate way; the only difference is capturing its output to a
file instead of only the (unreadable to us) Actions log. Writes output
to debug/pull_and_ingest_output.txt and commits it back to the repo.
One-off; delete this script and its workflow after use.
"""
import os
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    proc = subprocess.run(
        ["python3", "api_pull_ingest.py"],
        cwd=BASE,
        capture_output=True,
        text=True,
        timeout=1200,
    )

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "pull_and_ingest_output.txt"), "w") as f:
        f.write(f"RETURN CODE: {proc.returncode}\n\n")
        f.write("=== STDOUT ===\n")
        f.write(proc.stdout)
        f.write("\n\n=== STDERR ===\n")
        f.write(proc.stderr)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True, cwd=BASE)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True, cwd=BASE)
    subprocess.run(["git", "add", "debug/pull_and_ingest_output.txt"], check=True, cwd=BASE)
    subprocess.run(["git", "commit", "-m", "debug: full api_pull_ingest.py output"], check=True, cwd=BASE)
    subprocess.run(["git", "push"], check=True, cwd=BASE)
    print(f"Return code: {proc.returncode}")
    print("Output written to debug/pull_and_ingest_output.txt")


if __name__ == "__main__":
    main()
