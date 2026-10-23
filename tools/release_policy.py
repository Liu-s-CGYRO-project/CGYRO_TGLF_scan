"""Installer size policies shared by build tools, not solver/runtime limits.

The complete project carries both modules; its 2 MiB code budget is distinct
from the older manager bootstrap's decimal 1 MB transport contract. Full fonts
remain separate assets. Standalone installers embed these values at build time
and must not depend on this source-checkout module at the user's endpoint.
"""
MAX_PROJECT_PACKAGE_BYTES = 2 * 1024 * 1024
MAX_MANAGER_BOOTSTRAP_BYTES = 1_000_000
