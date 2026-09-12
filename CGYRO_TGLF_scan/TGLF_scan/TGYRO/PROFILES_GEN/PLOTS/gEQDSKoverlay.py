# -*-Python-*-
# Created by meneghini at 2015/03/28 18:01

root['OUTPUTS']['input.gacode'].plot_geo(lw=2, color='r')
if gEQDSK is not None:
    gEQDSK.plot(only2D=True, color='k')
else:
    print('no gEQDSK to overlay')
