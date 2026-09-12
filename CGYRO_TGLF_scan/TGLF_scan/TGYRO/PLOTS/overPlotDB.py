# -*-Python-*-
# Created by meneghini at 11 Sep 2015  12:04

defaultVars(funcName='plotTGYROfinal_profiles')

func = root['PLOTS'][funcName]

for runid in root['RUN_DB']:
    output = root['RUN_DB'][runid]['OUTPUTS']['output']
    print(re.sub('_', ' ', re.sub('TGYRO', '', re.sub('plot', '', funcName))) + ': ' + runid)
    if funcName == 'plotTGYROfinal_profiles':
        func.plot(output=output, plot_kw={'label': runid})
    else:
        func.plotFigure(re.sub('_', ' ', re.sub('TGYRO', '', re.sub('plot', '', funcName))) + ': ' + runid, output=output)
