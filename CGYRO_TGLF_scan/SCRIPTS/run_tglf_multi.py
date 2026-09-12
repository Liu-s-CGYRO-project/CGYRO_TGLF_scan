"""Generate/run selected cases. Solver work starts only from an explicit GUI action."""
from OMFITlib_tglf_multi_run import OMFITRunner, run_selected

defaultVars(action='all')
runner = OMFITRunner(root, OMFITx, OMFITgacode, OMFITascii, OMFITtglf, OMFITworkDir, SERVER, OMFITtree)
run_selected(root, runner, action, OMFITtree, progress=printi)
