# plot flux(n) & flux(t)
import sys
import numpy as np
num2str_xj = root['PLOTS']['CGYROscan']['assist']['cgyro_read_xj'].runNoGUI()['num2str_xj']
#sys.path.append('/home/users/xiangjian/mymodule/CGYRO_SCAN/PLOTS/CGYROalone/assist')
#sys.path.append('/home/users/xiangjian/mymodule/CGYRO_SCAN/PLOTS/CGYROscan/assist')
f = open(root['PLOTS']['CGYROalone']['assist']['getglobal.py'].filename, 'r')
for line in f:
    exec(line)
f.close()
icgyro=root['SETTINGS']['SETUP']['icgyro']
if icgyro==1:
    root['PLOTS']['CGYROalone']['assist']['collect.py'].run()
else:
    root['PLOTS']['CGYROalone']['assist']['collect_gyro.py'].run()
# check to see how many fields that all the cases have in common
n_field=3

for k_case in range(n_case):
    casek = outputs[case_plot[k_case]]
    if icgyro==1:
        n_field=min(len(casek['field_tags']),n_field)
    else:
        n_field=min(len(casek['tagfieldtext']),n_field)


# plot
for i_field in arange(n_field):
    figure('$'+field_name[i_field]+'$')
    for i_channel in range(n_channel):
# flux versus time
        ax=subplot(n_channel,2,2*i_channel+1)
        for k_case in range(n_case):
            print(case_plot[k_case])
            casek=outputs[case_plot[k_case]]
            kinetic_chan=channel[i_channel].split('_')[0] # must be Q, Gamma or Pi
            speci=int(channel[i_channel].split('_')[1])         # species
            casek.get_flux_t(i_field=i_field,i_species=speci-1)
            cmd1='plot(casek.t,casek.'+kinetic_chan+'_t,lab[k_case],linewidth=lw,label=case_plot[k_case])'
            #cmd2='plot(array([casek.ind_t_ave[0],casek.ind_t_ave[-1]]),array([casek.'+kinetic_chan+'_t_ave,casek.'+kinetic_chan+'_t_ave]),labd[k_case],linewidth=lw)'
            cmd2='plot(np.asarray(casek.t)[[casek.ind_t_ave[0],casek.ind_t_ave[-1]]],array([casek.'+kinetic_chan+'_t_ave,casek.'+kinetic_chan+'_t_ave]),labd[k_case],linewidth=lw)'
            exec('value_ave=casek.'+kinetic_chan+'_t_ave')
            exec ('value_std=casek.' + kinetic_chan + '_t_std')
            exec(cmd1)  # plot flux vs time
            exec (cmd2) # plot the flux averaged value
            ax.set_xscale(tick_scale[root['SETTINGS']['PLOTS']['ilogx']])
            ax.set_yscale(tick_scale[root['SETTINGS']['PLOTS']['ilogy']])
            text(casek.t[-1], value_ave,num2str_xj(value_ave,effnum)+'+-'+num2str_xj(value_std,effnum), fontsize = fs2,color=labd[k_case][-1])
            print(num2str_xj(value_ave,1)+'+-'+num2str_xj(value_std,effnum))
            if k_case == n_case-1:
                xlabel('$time(a/c_s)$', fontsize=fs1, family='serif')
        xticks(fontsize=fs2)
        yticks(fontsize=fs2)
        if icgyro==1:
            charge = casek['input.cgyro.gen']['Z_' + str(speci)]
        else:
            if speci==1:
                charge=casek['input.gyro.gen']['Z']
            else:
                charge=casek['input.gyro.gen']['Z_'+str(speci)]
        spec_name = ion_name[int(charge)]
        ylabel('$' + channel[i_channel].split('_')[0] + '_{' + spec_name + '}$', fontsize=fs1)
        legend(loc=0, fontsize=fs2).draggable(True)
# flux versus n
        ax=subplot(n_channel, 2, 2*i_channel+2)
        for k_case in range(n_case):
            casek=outputs[case_plot[k_case]]
            kinetic_chan=channel[i_channel].split('_')[0] # must be Q, Gamma or Pi
            speci=int(channel[i_channel].split('_')[1])         # species
            casek.get_flux_n(i_field=i_field,i_species=speci-1)
            cmd1='plot(casek.ky,casek.'+kinetic_chan+'_n_ave, labo[k_case], linewidth=lw, label=case_plot[k_case])'
            exec(cmd1)
            ax.set_xscale(tick_scale[root['SETTINGS']['PLOTS']['ilogx']])
            ax.set_yscale(tick_scale[root['SETTINGS']['PLOTS']['ilogy']])
            if k_case==n_case-1:
                xlabel('$k_y\\rho_s$', fontsize=fs1, family='serif')
        xticks(fontsize=fs2)
        yticks(fontsize=fs2)

# total flux over all fields
figure('$sum over field$')
for i_channel in range(n_channel):
# flux versus time
    ax=subplot(n_channel,2,2*i_channel+1)
    for k_case in range(n_case):
        print(case_plot[k_case])
        casek=outputs[case_plot[k_case]]
        kinetic_chan=channel[i_channel].split('_')[0] # must be Q, Gamma or Pi
        speci=int(channel[i_channel].split('_')[1])         # species
        casek.get_flux_t(i_field=-1,i_species=speci-1)
        cmd1='plot(casek.t,casek.'+kinetic_chan+'_t,lab[k_case],linewidth=lw,label=case_plot[k_case])'
        #cmd2='plot(array([casek.ind_t_ave[0],casek.ind_t_ave[-1]]),array([casek.'+kinetic_chan+'_t_ave,casek.'+kinetic_chan+'_t_ave]),labd[k_case],linewidth=lw)'
        cmd2='plot(np.asarray(casek.t)[[casek.ind_t_ave[0],casek.ind_t_ave[-1]]],array([casek.'+kinetic_chan+'_t_ave,casek.'+kinetic_chan+'_t_ave]),labd[k_case],linewidth=lw)'
        exec('value_ave=casek.'+kinetic_chan+'_t_ave')
        exec ('value_std=casek.' + kinetic_chan + '_t_std')
        exec(cmd1)  # plot flux vs time
        exec (cmd2) # plot the flux averaged value
        ax.set_xscale(tick_scale[root['SETTINGS']['PLOTS']['ilogx']])
        ax.set_yscale(tick_scale[root['SETTINGS']['PLOTS']['ilogy']])
        text(casek.t[-1], value_ave,num2str_xj(value_ave,effnum)+'+-'+num2str_xj(value_std,effnum), fontsize = fs2,color=labd[k_case][-1])
        print(num2str_xj(value_ave,1)+'+-'+num2str_xj(value_std,effnum))
        if k_case == n_case-1:
            xlabel('$time(a/c_s)$', fontsize=fs1, family='serif')
    xticks(fontsize=fs2)
    yticks(fontsize=fs2)
    if icgyro==1:
        charge = casek['input.cgyro.gen']['Z_' + str(speci)]
    else:
        if speci==1:
            charge=casek['input.gyro.gen']['Z']
        else:
            charge=casek['input.gyro.gen']['Z_'+str(speci)]
    spec_name = ion_name[int(charge)]
    ylabel('$' + channel[i_channel].split('_')[0] + '_{' + spec_name + '}$', fontsize=fs1)
    legend(loc=0, fontsize=fs2).draggable(True)
# flux versus n
    ax=subplot(n_channel, 2, 2*i_channel+2)
    for k_case in range(n_case):
        casek=outputs[case_plot[k_case]]
        kinetic_chan=channel[i_channel].split('_')[0] # must be Q, Gamma or Pi
        speci=int(channel[i_channel].split('_')[1])         # species
        casek.get_flux_n(i_field=-1,i_species=speci-1)
        cmd1='plot(casek.ky,casek.'+kinetic_chan+'_n_ave, labo[k_case], linewidth=lw, label=case_plot[k_case])'
        exec(cmd1)
        ax.set_xscale(tick_scale[root['SETTINGS']['PLOTS']['ilogx']])
        ax.set_yscale(tick_scale[root['SETTINGS']['PLOTS']['ilogy']])
        if k_case==n_case-1:
            xlabel('$k_y\\rho_s$', fontsize=fs1, family='serif')
    xticks(fontsize=fs2)
    yticks(fontsize=fs2)
print(casek.ind_t_ave)
