# -*-Python-*-
# Created by prattq at 15 Aug 2022  16:05

"""
This script extends the standalone TGLF module's "plotScanSpec" plotting script to the TGLF_scan module.

defaultVars parameters
----------------------
:param rho: rho value for the scan to plot.
:param param: scan parameter for the given rho.
"""

defaultVars(
    rho=root['SETTINGS']['PHYSICS']['rho'],
    param=root['TGLF']['SETTINGS']['PHYSICS']['scanParameter'],
)

assert rho in root['scanResults_spectra'], f"rho = {rho} does not exist in root['scanResults_spectra']"
assert param in root['scanResults_spectra'][rho], f"param: '{param}' does not exist in root['scanResults_spectra'][{rho}]"

# Move the scan results to the sub module,
root['TGLF'].setdefault('scanResults_spectra', OMFITtree())
# no need for a deepcopy here I think,
root['TGLF']['scanResults_spectra'][param] = root['scanResults_spectra'][rho][param]
# call the existing script with the TGLF_scan = True kwarg
out = root['TGLF']['PLOTS']['plotScanSpec'].run(param=param, TGLF_scan=True, plot_settings=root['SETTINGS'].get('PLOTS', {}))

# update the figure notebook with cornernotes,
fn = out['fn']
for f in fn:
    # make it the current figure by referencing it,
    cornernote(text=f"{param} scan, rho = {rho}", root='', ax=f.get_axes()[-1])
fn[0].canvas.draw()  # force a draw on the 0th figure for the cn to show up.
