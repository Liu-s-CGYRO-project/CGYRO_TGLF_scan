# -*-Python-*-
# Created by sciortinof at 24 Jul 2019  16:50

"""
Select quantities from a list of possibilities, taken from a dictionary indicated in 'dictionary_to_read'.
The input 'dictionary_to_write' indicates the name of the tree location where the selected quantities
from 'dictionary_to_read' should be written.

Inspired by the TGLF constraints_GUI.py by smithsp.
"""

defaultVars(dictionary_to_read=None, dictionary_to_write='scan_vars_to_plot')

if dictionary_to_read is None:
    raise OMFITexception('Must provide tree containing the results of transport coefficient scans!')


def add_quantity(location):
    if eval(location):
        root.setdefault(dictionary_to_write, {})[eval(location)] = eval(location)
    del scratch[dictionary_to_write + '_add_quantity']


OMFITx.ComboBox(
    "scratch['%s_add_quantity']" % dictionary_to_write,
    [''] + [k for k, v in sorted(dictionary_to_read.items()) if not k.startswith('__') and not is_int(v)],
    lbl='添加物理量',
    postcommand=add_quantity,
    help='Choose a scan output variable to be plotted.',
    default='',
    updateGUI=True,
)

if dictionary_to_write in root:
    if len(root[dictionary_to_write]):

        def delete_quantity(location):
            if eval(location):
                del root[dictionary_to_write][eval(location)]
                if not len(root[dictionary_to_write]):
                    del scratch[dictionary_to_write + '_delete_quantity']
                else:
                    scratch[dictionary_to_write + '_delete_quantity'] = list(root[dictionary_to_write].keys())[0]

        OMFITx.ComboBox(
            "scratch['%s_delete_quantity']" % dictionary_to_write,
            [''] + sorted(root[dictionary_to_write].keys()),
            lbl='删除物理量',
            help="Click on a quantity to eliminate it from the list",
            postcommand=delete_quantity,
            default='',
            updateGUI=True,
        )

    for k in root[dictionary_to_write]:
        OMFITx.Entry(
            "root['%s']['%s']" % (dictionary_to_write, k),
            lbl=k,
            help='Scan output variable to be plotted. Set the plot label in the second field.',
        )
