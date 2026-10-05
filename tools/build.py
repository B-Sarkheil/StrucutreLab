"""Build packages into dist/.

TODO:
  - zip src/ -> app-<version>.zip, compute sha256
  - build runtime from runtime/requirements.txt (uv) -> runtime-<hash>.zip, sha256
  - write latest.json LAST (so a half-published version is never seen)
"""
