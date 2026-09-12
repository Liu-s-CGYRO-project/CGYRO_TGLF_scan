# -*-Python-*-
# Created by grierson at 13 Aug 2017  14:18

"""
This script modifies (adds, removes) ions from a GACODE
input.gacode file.  The header text is unchanged but
the species values are modified to enforce quasineutrality
and when an ion is added, its temperature is set equal to
the first ion.  When an ion is removed, its temperature is
set to zero.

defaultVars parameters
----------------------
ion_num - Ion number in list, i.e. 3 for D, C, X
name - Ion name, i.e. D, C, He
Z - Ion charge, i.e. 1, 6, 2, ...
mass - Ion mass i.e. 2, 12, 4
concen - Ion concentration nX/ne
thermal - Thermal or fast species
aoLn - (optional) normalized inverse scale length of the profile.  Necessary for
 impurity transport studies when you need a finite gradient for computing D, V.
 If set, then the profile has the average concentration set at the boundary rho=1
isl_mul (optional) multiply the inverse scale length of the ion density profile as specified by aoLn_from
isl_add (optional) add to the inverse scale length of the ion density profile as specified by aoLn_from
aoLn_from (optional) specify a species to take the density profile from as starting point for the added profile (as a string or as an index)
z_eff (optional) add ion to reach a certain z_eff
remove_density_from_ion ion name or number from which to remove density (numbering before adding the new ion)
temperature_and_velocities_from_ion ion name or number from which the temperature and velocities are copied from (numbering before adding the new ion)
add - True to add an ion, else False to remove an ion
"""
defaultVars(
    ion_num=None,
    name=None,
    Z=None,
    mass=None,
    concen=None,
    thermal=True,
    aoLn=None,
    isl_mul=None,
    isl_add=None,
    aoLn_from=None,
    z_eff=None,
    add=True,
    reset=False,
)

# First make sure we can reset
if reset:
    # Place the *.orig files back and remove backups
    if 'input.gacode.orig' in root['OUTPUTS']:
        printi('Replacing input.gacode with input.gacode.orig')
        root['OUTPUTS']['input.gacode'] = root['OUTPUTS'].pop('input.gacode.orig')
    if 'input.gacode_base.orig' in root['OUTPUTS']:
        printi('Replacing input.gacode_base with input.gacode_base.orig')
        root['OUTPUTS']['input.gacode_base'] = root['OUTPUTS'].pop('input.gacode_base.orig')
    # Remove modified input.gacode
    if 'input.gacode.mod' in root['OUTPUTS']:
        printi('Removing input.gacode.mod')
        del root['OUTPUTS']['input.gacode.mod']
    # reset the reorder ions option in SETTINGS
    ions = root['OUTPUTS']['input.gacode']['IONS']
    root['SETTINGS']['PHYSICS']['reorder_ion_names'] = [ions[i][0] for i in ions]
    OMFITx.End()
else:
    # Backup original input.gacode

    if 'input.gacode.orig' not in root['OUTPUTS']:
        printi('Backing up input.gacode')
        root['OUTPUTS']['input.gacode.orig'] = copy.deepcopy(root['OUTPUTS']['input.gacode'])
    if 'input.gacode_base' not in root['OUTPUTS']:
        printi('Backing up input.gacode_base')
        root['OUTPUTS']['input.gacode_base'] = copy.deepcopy(root['OUTPUTS']['input.gacode.orig'])
    if 'input.gacode_base.orig' not in root['OUTPUTS']:
        printi('Backing up input.gacode_base.orig')
        root['OUTPUTS']['input.gacode_base.orig'] = copy.deepcopy(root['OUTPUTS']['input.gacode_base'])

# If there's an existing modified input.gacode, then remove it to avoid false
# sense of success if this script fails
if 'input.gacode.mod' in root['OUTPUTS']:
    del root['OUTPUTS']['input.gacode.mod']

# Copy input.gacode keeping same file name
root['OUTPUTS']['input.gacode.mod'] = input_mod = copy.deepcopy(root['OUTPUTS']['input.gacode'])

# ADD
if add:
    input_mod.add_ion(
        ion_num,
        name,
        Z,
        mass,
        concentration=concen,
        thermal=thermal,
        aoLn=aoLn,
        isl_mul=isl_mul,
        isl_add=isl_add,
        aoLn_from=aoLn_from,
        z_eff=z_eff,
        remove_density_from_ion=1,
        temperature_and_velocities_from_ion=1,
    )
# DELETE
else:
    input_mod.del_ion(name + ['[fast]', ''][thermal], add_density_to_ion=1)

# Finally clobber input.gacode and input.proifles.base
root['OUTPUTS']['input.gacode'] = root['OUTPUTS'].pop('input.gacode.mod')
root['OUTPUTS']['input.gacode_base'] = copy.deepcopy(root['OUTPUTS']['input.gacode'])

# set order of ion names in the tree
root['SETTINGS']['PHYSICS']['reorder_ion_names'] = root['OUTPUTS']['input.gacode'].ion_names()
