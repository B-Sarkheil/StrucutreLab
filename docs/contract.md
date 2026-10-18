# Frozen contract: bootstrap <-> app

Changing anything here breaks every installed copy and needs a re-install by IT.

## Layout on the user machine
```
%LocalAppData%\StructureLab\
  bootstrap\          Python (embeddable) + launcher.py
  runtime\<hash>\    Python libraries
  app\<version>\     src package
```

## Functions called by the launcher
- `src.__main__.main() -> int`
- `src.__main__.ping_app() -> bool` (always True; self-check after update)

## latest.json (server)
Fields: `channel`, `min_bootstrap_version`, `app{version,file,sha256}`, `runtime{id,file,sha256}`.
Versions are three-part (`packaging.version`). Written last by the publish step.

## Update rules
Download to temp, verify sha256, extract, atomic rename, self-check, auto rollback,
fail-open if the server is unreachable, best-effort server log.

## Open questions for IT
- Is server write permission Write Data only? (affects publishing)
- AppLocker rules on .pyd / .dll in AppData.
