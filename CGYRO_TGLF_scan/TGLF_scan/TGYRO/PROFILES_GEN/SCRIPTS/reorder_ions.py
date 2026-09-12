# -*-Python-*-
# Created by smithsp at 2014/05/12 13:39

if root['SETTINGS']['PHYSICS']['reorder_ion_names'] is nan:
    root['OUTPUTS'].clear()
    root['SETTINGS']['PHYSICS']['reorder_ion_names'] = None

if 'input.gacode' in root['OUTPUTS']:

    if root['SETTINGS']['PHYSICS']['reorder_ion_names']:
        names = root['OUTPUTS']['input.gacode'].ion_names()

        if 'D' in names and 'T' in names and 'DT' in root['SETTINGS']['PHYSICS']['reorder_ion_names']:
            root['OUTPUTS']['input.gacode'].merge_DT()
            names = root['OUTPUTS']['input.gacode'].ion_names()

        for item in names:
            if item not in root['SETTINGS']['PHYSICS']['reorder_ion_names']:
                root['OUTPUTS']['input.gacode'].del_ion(item)
            names = root['OUTPUTS']['input.gacode'].ion_names()

    root['OUTPUTS']['input.gacode'].reorder_ions(root['SETTINGS']['PHYSICS']['reorder_ion_names'])
