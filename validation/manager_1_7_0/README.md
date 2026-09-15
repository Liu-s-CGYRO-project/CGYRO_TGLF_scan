# Manager 1.7.0 validation

- `manager-tests.log`: 167 Linux regression tests passed.
- `native-execution.json`: 20 checks using the unchanged OMFIT execution and import bodies, including incremental installation after import-cache cleanup.
- `native-tk.json` and `layout.json`: native Tk patches and seven font/scale/embedding configurations. `incremental-update.png` shows a synthetic update preview, not measured download volume.
- `compatibility.json`: Python 3.9 syntax and OMFIT registration audit.
- `packages.json`: built package, native ZIP entry, cold GUI startup, and retained project data/settings checks; 290 scientific files unchanged.
- `incremental-packages.json`: rebuilt the actual 1.7.0 distribution from the actual 1.6.0 files using the new updater. Fourteen files downloaded (53,446 compressed bytes), twenty reused, and a 9,329-byte manifest, versus a 92,120-byte complete Linux package. Every assembled file matches the complete release; original files remain unchanged; GUI startup and activation/revert passed. This exercises the new backend against old files: a 1.6.0 client still needs a one-time full upgrade to gain incremental support.
- `native-reopen.json`: actual old/new GUI entry execution with native OMFIT import cleanup and Tk patches, in one Tk interpreter. The old window closed and the new version opened; calculation object identity, unsaved results, and manager settings remained intact. Module construction uses an adapter; this is not a complete remote OMFIT session or solver test.
