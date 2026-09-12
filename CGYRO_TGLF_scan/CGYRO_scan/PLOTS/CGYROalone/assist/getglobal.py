# some commonly used variables
pltnl=root['SETTINGS']['PLOTS']['nl']
t_ave=pltnl['t_ave']  # average over [1-t_ave,1]*time_tot
case_plot=pltnl['case_plot']
n_case=len(case_plot)
channel=pltnl['channel']  # which channel to be compared, including  Q_*, Gamma_*,Pi_*, multiple value is available
n_channel=len(channel)
outputs=root['OUTPUTS']['NonLinear']
freq_lin=pltnl['freq_lin']
tick_scale={0:'linear',1:'log'}
effnum=root['SETTINGS']['SETUP']['effnum']
fs1=24
fs2=20
fs3=16
lw=2
from matplotlib import colors as _cgyro_colors
_CGYRO_LINE_COLORS=['#F14040','#1A6FDF','#37AD6B','#B177DE','#CC9900','#00CBCC','#7D4E4E','#8E8E00','#FB6501','#6699CC','#6FB802']
_CGYRO_LINE_CODES=list('ABEFGIJKLMN')
_cgyro_colors.get_named_colors_mapping().update(dict(zip(_CGYRO_LINE_CODES,_CGYRO_LINE_COLORS)))
lab=['-'+c for c in _CGYRO_LINE_CODES]+['-'+c for c in _CGYRO_LINE_CODES]
labd=['--'+c for c in _CGYRO_LINE_CODES]+['--'+c for c in _CGYRO_LINE_CODES]
labo=['-'+c+'o' for c in _CGYRO_LINE_CODES]+['-'+c+'o' for c in _CGYRO_LINE_CODES]
ion_name={1:'D',2:'He',-1:'e',6:'C',18:'Ar',10:'Ne',4:'Be',28:'Ni'}
field_name={0:'phi',1:'A_{||}',2:'B_{||}'}
moment_name={0:'n',1:'p',2:'v'}
