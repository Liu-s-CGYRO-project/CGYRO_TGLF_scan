# -*-Python-*-
# Created by smithsp at 2015/03/10 11:52

OMFITx.TitleGUI('读取已有 TGYRO 运行')


def load_existing(location):
    d, server, tunnel = eval(location)
    root['SCRIPTS']['load_remote'].run(server=server, tunnel=tunnel, remote_dir=d, load_input_gacode=True)
    root['GUIS']['TGYROgui'].run()


OMFITx.FilePicker(
    "scratch['existing_dir']",
    lbl='已有 TGYRO 运行目录',
    default='',
    transferRemoteFile=None,
    directory=True,
    postcommand=load_existing,
)
