# -*-Python-*-
# Created by sciortinof at 29 Jul 2019  11:13

"""
This script reloads the result of TGLF runs that were used to find particle transport coefficients.
"""

runs_label = root['SETTINGS']['PHYSICS']['runs_label']

if len(root['TGLF_SCAN_DB']) and runs_label in root['TGLF_SCAN_DB']:
    print("Loading cached transport coefficients in root['TGLF_SCAN_DB'][`%s`]" % runs_label)
    settings = root['TGLF_SCAN_DB'][runs_label]['PHYSICS_SETTINGS']

    for key, val in settings.items():
        root['SETTINGS']['PHYSICS'][key] = val
