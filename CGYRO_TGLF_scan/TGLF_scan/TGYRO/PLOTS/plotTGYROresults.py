# -*-Python-*-
# Created by meneghini at 2013/04/02 11:29

defaultVars(output=root['OUTPUTS']['output'], plots=['fluxes'])

# use the default plot function defined in omfit_tree.py
if 'fluxes' in plots:
    output.plot()
