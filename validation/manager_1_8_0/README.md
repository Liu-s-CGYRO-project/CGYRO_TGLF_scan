# Manager 1.8.0 validation

- `manager-tests.log`: 169 Linux regression tests passed, including author selection combined with search/sorting, correct release identity after filtering, and clearing obsolete author filters when a library changes.
- `layout.json`: eight font/scale/embedding configurations checked across all four pages and the proxy/update dialogs. Empty-state hint rows have 6–9 pixels between their widget bounds plus internal padding. One case bypasses the preferred-font catalogue to exercise Tk's actual Chinese fallback-face lookup.
- `library-empty-14.png` and `library-empty-11.png`: actual Linux Tk windows showing author selection and separated Chinese hint lines. `incremental-update.png` uses synthetic release notes to inspect the update-dialog layout.
- `native-tk.json` and `native-execution.json`: native OMFIT Tk patches and 20 execution checks; adapters are used for the host session, not a complete remote OMFIT runtime.
- `compatibility.json`: 268 production Python files audited for Python 3.9 syntax and OMFIT registration.
- `packages.json`: actual release ZIP entry, isolated GUI startup and old-project result/settings preservation checks; 290 scientific files unchanged and no calculation data in the published package.
- `incremental-packages.json`: the unmodified 1.7.0 client rebuilt 1.8.0 from eight changed files (41,056 compressed bytes) and 26 local files. Including the manifest, the transfer is 50,385 bytes versus a 93,741-byte complete package. Every assembled file matches the complete release; GUI startup, activation/revert and old-file preservation passed.
