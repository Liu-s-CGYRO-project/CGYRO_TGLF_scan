# -*-Python-*-
# Created by meneghini at 17 Apr 2018  22:55


def numd_ion_names():
    numd_ion_names = []
    if 'input.gacode' in root['OUTPUTS']:
        numd_ion_names = root['OUTPUTS']['input.gacode'].ion_names()
        reorder = root['SETTINGS']['PHYSICS']['reorder_ion_names']
        if not iterable(reorder) or tuple(reorder) not in itertools.permutations(numd_ion_names):
            root['SETTINGS']['PHYSICS']['reorder_ion_names'] = numd_ion_names
    return numd_ion_names
