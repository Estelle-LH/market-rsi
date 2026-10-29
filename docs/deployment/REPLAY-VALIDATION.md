# Read-only replay validation

Replay validation reads a declared, hash-bound set of local files. It checks identity and journal hash chains, compares a saved snapshot with pure replay, and verifies that work-completion evidence agrees. Missing or inconsistent inputs fail.

The reader prohibits write-mode opens, deletion, renaming and filesystem repair. Pending temporary files are preserved when a read would otherwise trigger recovery. Unknown results never become success through repair or a guessed empty state. Directory symlinks and undeclared journal members are rejected before replay.

Sixteen focused checks use newly created synthetic metadata. They cover matching replay, active claims, changed hash chains, missing snapshots, changed evidence, lock contention, pending-file preservation, directory boundaries and explicit runtime bindings. File bytes remain unchanged. These are local protocol checks; workload admission, deployment acceptance and performance measurement remain separate.

No workload is launched by this helper.
