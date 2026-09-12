# -*-Python-*-
# Created by thomek at 27 Sep 2016  16:43

# Residual Convergence
fig = plt.figure()
title('Global Residual')
xlabel('Iteration')
ylabel('Residual')
yscale('log')
mk = ['o', '^', 's', 'D', 'x', '.', 'v', '8', '+', '*']
for i, run in enumerate(scratch['plot_runids']):
    if i >= len(mk):
        printi('This will plot only {} runs at once'.format(len(mk)))
    else:
        output = root['RUN_DB'][run]['OUTPUTS']['output']
        nit = len(output['convergence'])
        plot(arange(nit), output['convergence'], marker=mk[i], label=run)
        legend(loc='best').draggable(True)
