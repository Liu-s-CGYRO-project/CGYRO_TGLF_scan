"""Retired byte-level archive compactor; use native archive maintenance.

Historical versions rewrote OMFITsave rows independently of the live archive
contract. They cannot safely implement current browser expressions, frozen
input ownership, scan identity recovery and continuation retention together.
Keep this entry point as an explicit guard for old commands, rather than
silently producing an archive with only part of the current format.
"""
import argparse


MIGRATION_MESSAGE = (
    'This legacy ZIP compactor is retired; no files were read or changed. '
    'Open the original project in OMFIT, update with the matching release-specific '
    'omfit-maintain-<version>.py, then Save As a new ZIP. '
    'An already updated project can run '
    "OMFIT['CGYRO_TGLF_scan']['SCRIPTS']['compact_cgyro_storage'].run(). "
    'See COMMAND_BOX_COMPACTION.md.'
)


def compact(source, output, code_project, report_path):
    """Reject the old signature before opening even the source or report path."""
    raise RuntimeError(MIGRATION_MESSAGE)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--output', required=True)
    parser.add_argument('--code-project', required=True)
    parser.add_argument('--report', required=True)
    parser.parse_args()
    parser.exit(2, MIGRATION_MESSAGE + '\n')
