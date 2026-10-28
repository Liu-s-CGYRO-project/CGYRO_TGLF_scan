from OMFITlib_gui_api import task_action
from OMFITlib_gui_api import adapt, gui_view
OMFITx = adapt(OMFITx)
# -*-Python-*-
# Created by smithsp at 2015/03/10 11:52

OMFITx.TitleGUI('读取已有 TGYRO 运行')


def load_existing(location):
    d, server, tunnel = eval(location)
    task_action(root['SCRIPTS']['load_remote'], server=server, tunnel=tunnel, remote_dir=d, load_input_gacode=True)
    gui_view(root['GUIS']['TGYROgui'])


OMFITx.FilePicker(
    "scratch['existing_dir']",
    lbl='已有 TGYRO 运行目录',
    default='',
    transferRemoteFile=None,
    directory=True,
    postcommand=load_existing,
)
