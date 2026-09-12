# this script should run after the main.py
TGLF=root['OUTPUTS']['TGYRO']['TGLF']
for k in range(1,14):
    print(k)
    tglf=TGLF['out.tglf.localdump_'+str(k)]
    print(str(tglf['RLTS_2'])+'  '+str(tglf['RLTS_1'])+'  '+str(tglf['RLNS_1'])+'  '+str(tglf['SHAT_SA'])+'  '+str(tglf['Q_SA'])+'  '+str(tglf['BETAE'])+'  '+str(tglf['XNUE'])+'  '+str(tglf['ALPHA_SA']))
    print('\n')
