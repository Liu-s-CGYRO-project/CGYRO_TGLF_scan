# -*-Python-*-
# Created by smithsp at 2015/03/10 11:52

OMFITx.TitleGUI('TGYRO load existing run GUI')


def load_existing(location):
    d, server, tunnel = eval(location)
    root['SCRIPTS']['load_remote'].run(server=server, tunnel=tunnel, remote_dir=d, load_input_gacode=True)
    root['GUIS']['TGYROgui'].run()


OMFITx.FilePicker(
    "scratch['existing_dir']",
    lbl='Directory of existing TGYRO run',
    default='',
    transferRemoteFile=None,
    directory=True,
    postcommand=load_existing,
)
