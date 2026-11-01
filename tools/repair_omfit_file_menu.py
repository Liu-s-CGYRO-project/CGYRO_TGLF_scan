"""Remove project traversal and filesystem I/O from the native File menu.

In an existing OMFIT session call install(OMFITaux['GUI'], OMFIT). This changes
only that menu's postcommand, lasts until the main GUI is rebuilt, and can be
undone with restore(OMFITaux['GUI']). It does not edit a project or shared core.
The command-line mode writes a candidate source file for review, never replaces
the original. The explicit reload/export actions retain module discovery.
"""
import argparse
import ast
from pathlib import Path


OLD_UPDATE = '''        def update():
            self.force_selection()
            # export/reload modules
            if len(OMFIT.moduleDict()):
                filemenu.entryconfig(10, state=tk.NORMAL)
                filemenu.entryconfig(11, state=tk.NORMAL)
            else:
                filemenu.entryconfig(10, state=tk.DISABLED)
                filemenu.entryconfig(11, state=tk.DISABLED)
            # save
            if OMFIT.filename == '' or not os.access(OMFIT.filename, os.W_OK):
                filemenu.entryconfig(2, state=tk.DISABLED)
            else:
                filemenu.entryconfig(2, state=tk.NORMAL)

        filemenu.config(postcommand=update)
'''
NEW_UPDATE = '''        def update():
            # Opening File needs no selected object or recursive module list.
            # OMFITmodules discovers modules when invoked; quickSave checks
            # write access when saving, not while opening a menu on NFS.
            filemenu.entryconfig(2, state=tk.NORMAL if OMFIT.filename else tk.DISABLED)

        filemenu.config(postcommand=update)
'''
MODULE_LOOKUP = '        moduleDict = OMFIT.moduleDict()\n'
MODULE_GUARD = '''        moduleDict = OMFIT.moduleDict()
        if not moduleDict:
            printi('No loaded modules to reload or export.')
            return

'''
STATE_ATTRIBUTE = '_file_menu_local_postcommand'


def patched_source(source):
    """Patch only the inspected File callback and move its empty-list check."""
    text = source.decode('utf-8')
    newline = '\r\n' if '\r\n' in text else '\n'
    text = text.replace('\r\n', '\n')
    if NEW_UPDATE in text and MODULE_GUARD in text and OLD_UPDATE not in text:
        return source
    if text.count(OLD_UPDATE) != 1 or text.count(MODULE_LOOKUP) != 1:
        raise ValueError('Unrecognized native File menu implementation; no change made')
    tree = ast.parse(text)
    gui = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'OMFITgui')
    method = next(node for node in gui.body if isinstance(node, ast.FunctionDef) and node.name == 'OMFITmodules')
    lines = text.splitlines(keepends=True)
    # This native action creates its own window first; do not scan modules on
    # menu expansion, and do not create an empty dialog when no module exists.
    start = method.body[0].lineno - 1
    if lines[start] != '        top = tk.Toplevel(self.rootGUI)\n':
        raise ValueError('Unrecognized native module dialog implementation; no change made')
    lines.insert(start, MODULE_GUARD)
    text = ''.join(lines).replace(OLD_UPDATE, NEW_UPDATE, 1)
    # The first lookup is the inserted guard; remove the old action-local copy.
    position = text.index(MODULE_LOOKUP, text.index(MODULE_GUARD) + len(MODULE_GUARD))
    text = text[:position] + text[position:].replace(MODULE_LOOKUP, '', 1)
    compile(text, 'omfit_gui.py', 'exec')
    return text.replace('\n', newline).encode('utf-8')


def install(gui, project):
    """Use public Tk menu APIs; retain every action's original command."""
    menu = gui.filemenu
    if hasattr(menu, STATE_ATTRIBUTE):
        return 'already_installed'
    indices = {}
    for index in range(menu.index('end') + 1):
        if menu.type(index) == 'command':
            indices[menu.entrycget(index, 'label')] = index
    labels = ('Save project', 'Reload modules...', 'Export modules...')
    if any(label not in indices for label in labels):
        raise ValueError('Unrecognized File menu; no change made')
    original = str(menu.cget('postcommand'))
    states = {indices[label]: menu.entrycget(indices[label], 'state') for label in labels}

    def update():
        menu.entryconfigure(indices['Save project'], state='normal' if project.filename else 'disabled')

    menu.configure(postcommand=update)
    registered = str(menu.cget('postcommand'))
    setattr(menu, STATE_ATTRIBUTE, (original, registered, states))
    for label in labels[1:]:
        menu.entryconfigure(indices[label], state='normal')
    return 'installed'


def restore(gui):
    menu = gui.filemenu
    state = getattr(menu, STATE_ATTRIBUTE, None)
    if state is None:
        return 'not_installed'
    original, registered, states = state
    # Do not overwrite a later repair or a menu rebuilt by another component.
    if str(menu.cget('postcommand')) != registered:
        raise ValueError('File menu callback changed after installation; leave it unchanged')
    menu.configure(postcommand=original)
    for index, value in states.items():
        menu.entryconfigure(index, state=value)
    menu.deletecommand(registered)
    delattr(menu, STATE_ATTRIBUTE)
    return 'restored'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Inspected native omfit_gui.py')
    parser.add_argument('--output', type=Path, required=True, help='New candidate path; cannot already exist')
    args = parser.parse_args()
    data = patched_source(args.source.read_bytes())
    with args.output.open('xb') as stream:
        stream.write(data)
    print('Candidate written: ' + str(args.output))
    print('Original source and running OMFIT session are unchanged.')


if __name__ == '__main__':
    main()
