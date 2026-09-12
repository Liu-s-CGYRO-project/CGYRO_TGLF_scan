#import numpy as np
#import sys
#sys.path.append('/home/jianx/mymodule/TGLF_SCAN/PLOTS/assist')
#from tglf_read_xj import *
#def getglobal():
plots=root['SETTINGS']['PLOTS']
plt1d=plots['1d']  # type: object
plt2d=plots['2d']
physics=root['SETTINGS']['PHYSICS']
phy1d=physics['1d']
phy2d=physics['2d']
inputcgyro = root['INPUTS']['input.cgyro']
if plots['iflwphy']==1:
    plots['kyarr']=physics['kyarr']
    plots['ky_eigen']=physics['kyarr']
    plt1d['Para']=phy1d['Para']
    plt1d['Range']=phy1d['Range']
    plt1d['para_eigen']=phy1d['Range']
    plt2d['Para_x']=phy2d['Para_x']
    plt2d['Para_y']=phy2d['Para_y']
#    plt2d['Para_x_display']=phy2d['Para_x']
#    plt2d['Para_y_display']=phy2d['Para_y']
    plt2d['Range_x']=phy2d['Range_x']
    plt2d['Range_y']=phy2d['Range_y']
    plt2d['para_x_eigen']=phy2d['Range_x']
    plt2d['para_y_eigen']=phy2d['Range_y']
