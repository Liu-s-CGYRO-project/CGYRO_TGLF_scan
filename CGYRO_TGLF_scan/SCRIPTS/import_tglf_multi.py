"""Import snapshots of multiple profile files without modifying active inputs."""
from pathlib import Path
from OMFITlib_tglf_multi_data import import_files

defaultVars(files=None, directory=False)
if files is None:
    if directory:
        selected = tkFileDialog.askdirectory(parent=OMFITaux['rootGUI'], title='选择包含 input.gacode 的目录')
        files = sorted(str(path) for path in Path(selected).rglob('*') if path.is_file()
                       and (path.name == 'input.gacode' or path.name.endswith('.gacode'))) if selected else []
    else:
        files = tkFileDialog.askopenfilenames(parent=OMFITaux['rootGUI'], title='选择多个 input.gacode',
                                             filetypes=[('GACODE profiles', '*gacode*'), ('All files', '*')])
        if isinstance(files, str):
            files = OMFITaux['rootGUI'].tk.splitlist(files)
if files:
    import_files(root, files, OMFITgacode, OMFITtree)
