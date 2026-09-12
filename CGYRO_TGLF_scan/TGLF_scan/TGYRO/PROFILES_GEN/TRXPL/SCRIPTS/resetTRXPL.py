# -*-Python-*-
# Created by meneghini at 17 Sep 2015  16:26

defaultVars(soft=False)

if soft:
    print('Reset TRXPL (soft)')
else:
    print('Reset TRXPL')

root['INPUTS'].clear()
root['OUTPUTS'].clear()
