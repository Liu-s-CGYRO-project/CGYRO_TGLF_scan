# this script is used to plot the quasilinear flux weight
import numpy as np
import xarray as xr
import os
import sys

from OMFITlib_cgyro_read import *
with open(root['PLOTS']['CGYROscan']['assist']['getglobal.py'].filename, 'r') as _helper_source:
    exec(compile(_helper_source.read(), _helper_source.name, 'exec'), globals())
# get the data
for paraval_item in Range:
    for ky_item in kyarr:
        datanode=root['OUTPUTScan'][Para][num2str_xj(paraval_item,effnum)]['lin'][num2str_xj(ky_item,effnum)]
        dirname='para_'+num2str_xj(paraval_item,effnum)+'~ky_'+num2str_xj(ky_item,effnum)
        mounttree[dirname]=copy.deepcopy(datanode)

# get the value
nfield=3
Ge=zeros([3,num_ky,nRange]) # 3 is for the number of fields
Gi=zeros([3,num_ky,nRange]) # can be the sum of over species or just one species, depending on i_ion_species, shown below
Qe=zeros([3,num_ky,nRange]) #
Qi=zeros([3,num_ky,nRange]) #
Pe=zeros([3,num_ky,nRange]) #
Pi=zeros([3,num_ky,nRange]) #
i_ion_species=-1;                   # -1: sum over the species; positiva value: the index of the ion species, 1 for the fist species
Gamma_data = None
Q_data = None
Pi_data = None
species_labels = None
source_inputs = []
for p_ky in range(num_ky):
    range_sources = []
    for p_range in range(nRange):
        dirname='para_'+num2str_xj(Range[p_range],effnum)+'~ky_'+num2str_xj(kyarr[p_ky],effnum)
        case = mounttree[dirname]
        totals, raw, labels = ql_species_flux(case, setup['icgyro'], i_ion_species, nfield)
        if Gamma_data is None:
            species_labels = labels
            shape = (len(labels), nfield, num_ky, nRange)
            Gamma_data, Q_data, Pi_data = (np.zeros(shape) for _ in range(3))
        if labels != species_labels:
            raise ValueError('Species identity/order changes across linear scan')
        Gamma_data[:, :, p_ky, p_range] = raw['particle']
        Q_data[:, :, p_ky, p_range] = raw['energy']
        Pi_data[:, :, p_ky, p_range] = raw['momentum']
        for channel_name, channel in [('Ge', Ge), ('Gi', Gi), ('Qe', Qe), ('Qi', Qi), ('Pe', Pe), ('Pi', Pi)]:
            channel[:, p_ky, p_range] = totals[channel_name]
        generated = case['input.cgyro.gen' if setup['icgyro'] else 'input.gyro.gen']
        range_sources.append({str(key): generated[key] for key in generated.keys()})
    source_inputs.append(range_sources)
Channel_arr=['Pe','Pi','Ge','Gi','Qe','Qi']
# plots
for p_field in range(nfield):
    figure('field' + str(p_field))
    for k in range(1, 7):
        axk = subplot(3, 2, k)
        if idimplt==0:
            for p_range in range(nRange):
                print(p_range)
                cmd='axk.plot(kyarr,'+Channel_arr[k-1]+'[p_field].T[p_range],lab[p_range],label=str(Range[p_range]))'
                exec (cmd)
                if k==5 or k==6:
                    xlabel('$k_y$',fontsize=fs1,family='serif')
        else:
            for p_ky in range(num_ky):
                cmd = 'axk.plot(Range,' + Channel_arr[k - 1] + '[p_field][p_ky],lab[p_ky],label=str(kyarr[p_ky]))'
                exec (cmd)
                if k==5 or k==6:
                    xlabel(Para,fontsize=fs1,family='serif')
        axk.set_xscale(scale_dic[ilogx])
        axk.set_yscale(scale_dic[ilogy])
        xticks(fontsize=fs2,family='serif')
        yticks(fontsize=fs2,family='serif')
        if k==1 or k==3 or k==5:
            title(Channel_arr[k-1],fontsize=fs1,family='serif')
        else:
            if i_ion_species==-1:
                tag='-sum'
            else:
                tag='-ion_'+str(i_ion_species)
            title(Channel_arr[k-1]+tag,fontsize=fs1,family='serif')
    legend(loc=0,fontsize=fs2).set_draggable(True)
# plot the sum over all fields
figure('field-sum')
for k in range(1, 7):
    axk = subplot(3, 2, k)
    if idimplt==0:
        for p_range in range(nRange):
            print(p_range)
            # cmd='axk.plot(kyarr,'+Channel_arr[k-1]+'[p_field].T[p_range],lab[p_range],label=str(Range[p_range]))'
            cmd='axk.plot(kyarr,sum('+Channel_arr[k-1]+', axis=0).T[p_range],lab[p_range],linewidth=lw,label=str(Range[p_range]))'
            exec (cmd)
            if k==5 or k==6:
                xlabel('$k_y$',fontsize=fs1,family='serif')
    else:
        for p_ky in range(num_ky):
            cmd = 'axk.plot(Range,sum(' + Channel_arr[k - 1] + ',axis=0)[p_ky],lab[p_ky],linewidth=lw,label=str(kyarr[p_ky]))'
            exec (cmd)
            if k==5 or k==6:
                xlabel(Para,fontsize=fs1,family='serif')
    axk.set_xscale(scale_dic[ilogx])
    axk.set_yscale(scale_dic[ilogy])
    xticks(fontsize=fs2,family='serif')
    yticks(fontsize=fs2,family='serif')
    if k==1 or k==3 or k==5:
        title(Channel_arr[k-1],fontsize=fs1,family='serif')
    else:
        if i_ion_species==-1:
            tag='-sum(all ions)'
        else:
            tag='-ion_'+str(i_ion_species)
        title(Channel_arr[k-1]+tag,fontsize=fs1,family='serif')
legend(loc=0,fontsize=fs2).set_draggable(True)
#
figure('field-sum-ratio to Qe')
for k in range(1, 7):
    axk = subplot(3, 2, k)
    if idimplt==0:
        for p_range in range(nRange):
            print(p_range)
            # cmd='axk.plot(kyarr,'+Channel_arr[k-1]+'[p_field].T[p_range],lab[p_range],label=str(Range[p_range]))'
            cmd='axk.plot(kyarr,sum('+Channel_arr[k-1]+', axis=0).T[p_range]/sum(Qe,axis=0).T[p_range],lab[p_range],linewidth=lw,label=str(Range[p_range]))'
            exec (cmd)
            if k==5 or k==6:
                xlabel('$k_y$',fontsize=fs1,family='serif')
    else:
        for p_ky  in range(num_ky):
            cmd = 'axk.plot(Range,sum(' + Channel_arr[k - 1] + ',axis=0)[p_ky]/sum(Qe,axis=0)[p_ky],lab[p_ky],linewidth=lw,label=str(kyarr[p_ky]))'
            exec (cmd)
            if k==5 or k==6:
                xlabel(Para,fontsize=fs1,family='serif')
    axk.set_xscale(scale_dic[ilogx])
    axk.set_yscale(scale_dic[ilogy])
    xticks(fontsize=fs2,family='serif')
    yticks(fontsize=fs2,family='serif')
    if k==1 or k==3 or k==5:
        title(Channel_arr[k-1],fontsize=fs1,family='serif')
    else:
        if i_ion_species==-1:
            tag='-sum(all ions)'
        else:
            tag='-ion_'+str(i_ion_species)
        title(Channel_arr[k-1]+tag,fontsize=fs1,family='serif')
legend(loc=0,fontsize=fs2).set_draggable(True)

# write the flux out
iwriteflux=plots['iwriteflux']
if iwriteflux==1:
    fluxout=root['SETTINGS']['DEPENDENCIES']['fluxout']
    fid=open(fluxout,'w')
# firstly write the scanned parameter name into the file
    fid.write(Para)
    fid.write('\n')
# write the nRange and the para_val into the file
    fid.write(str(nRange))
    fid.write('\n')
    line=''
    for m in range(nRange):
        line=line+str(Range[m])+'    '
    fid.write(line)
    fid.write('\n')
# write the number of poloidal modes into the file for flux summation
    fid.write(str(nfield)+'    '+str(num_ky))
    fid.write('\n')
# write the flux spectrum into the file
# fromation: row number, num_ky
# colum: ky, ((pflux,Qe, Qi, Pi)*nmodes)*nRange)
    for k in range(num_ky):
        line=str(kyarr[k])
        for p in range(nRange):
            for n in range(nfield):
                line=line+'    '+str(Ge[n][k][p])+'    '+\
                                 str(Qe[n][k][p])+'    '+\
                                 str(Qi[n][k][p])+'    '+\
                                 str(Pi[n][k][p])
        fid.write(line)
        fid.write('\n')
    fid.close()
    print('write data done!')

# format fluxes as xarray with dimensions:
# (n_species, n_field, num_ky, nRange)
if Gamma_data is None:
    Gamma_data = np.stack([Ge, Gi], axis=0)
    Q_data = np.stack([Qe, Qi], axis=0)
    Pi_data = np.stack([Pe, Pi], axis=0)
    species_labels = ['electron', 'ion_sum']

field_index = np.arange(nfield)

QLW_Gamma = xr.DataArray(
    Gamma_data,
    dims=('n_species', 'n_field', 'num_ky', 'nRange'),
    coords={
        'n_species': species_labels,
        'n_field': field_index,
        'num_ky': kyarr,
        'nRange': Range,
    },
    name='QLW_Gamma',
)

QLW_Q = xr.DataArray(
    Q_data,
    dims=('n_species', 'n_field', 'num_ky', 'nRange'),
    coords={
        'n_species': species_labels,
        'n_field': field_index,
        'num_ky': kyarr,
        'nRange': Range,
    },
    name='QLW_Q',
)

QLW_Pi = xr.DataArray(
    Pi_data,
    dims=('n_species', 'n_field', 'num_ky', 'nRange'),
    coords={
        'n_species': species_labels,
        'n_field': field_index,
        'num_ky': kyarr,
        'nRange': Range,
    },
    name='QLW_Pi',
)

# Cache belongs to this project and contains the input of every source point.
root['QLW'] = OMFITtree({'Gamma': QLW_Gamma, 'Q': QLW_Q, 'Pi': QLW_Pi,
    'parameter': Para, 'source_inputs': source_inputs,
    'run_token': root.get('RUN_MANIFEST', {}).get('run_token', 'imported'),
    'species_labels': species_labels})
