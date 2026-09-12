# -*-Python-*-
# Created by smithsp at 08 Dec 2016  10:20

defaultVars(input_tglf=None)
if input_tglf is None:
    raise OMFITexception('Must provide input_tglf as input to this GUI')


def add_constraint(location):
    if eval(location):
        root.setdefault('constraint_vars', {})[eval(location)] = eval(location)
    del scratch['add_constraint']


OMFITx.ComboBox(
    "scratch['add_constraint']",
    [''] + [k for k, v in sorted(input_tglf.items()) if not k.startswith('__') and not is_int(v)],
    lbl="Add constraint",
    postcommand=add_constraint,
    help='Choose a variable that is constrained to be a function of other variables',
    default='',
    updateGUI=True,
)

if 'constraint_vars' in root:
    if len(root['constraint_vars']):

        def delete_constraint(location):
            if eval(location):
                del root['constraint_vars'][eval(location)]
                if not len(root['constraint_vars']):
                    del scratch['delete_constraint']
                else:
                    scratch['delete_constraint'] = list(root['constraint_vars'].keys())[0]

        OMFITx.ComboBox(
            "scratch['delete_constraint']",
            [''] + sorted(root['constraint_vars'].keys()),
            lbl="Delete constraint",
            postcommand=delete_constraint,
            default='',
            updateGUI=True,
        )

    for k in root['constraint_vars']:

        def check_constraint(s):
            if not isinstance(s, str):
                return False
            if s == k:
                return True
            for v in input_tglf:
                exec("%s = input_tglf['%s']" % (v, v))
            try:
                eval(s)
                if k in s:
                    printe('The variable itself is not allowed in the expresssion')
                    return False
                return True
            except Exception as _excp:
                printe(repr(_excp))
                return False

        OMFITx.Entry(
            "root['constraint_vars']['%s']" % k,
            lbl=k,
            help='Enter constraint on %s in terms of other variables' % k,
            check=check_constraint,
        )
