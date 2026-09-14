# this script is used to plot the quasilinear flux.
import sys
import xarray as xr
from OMFITlib_cgyro_read import *
with open(root['PLOTS']['CGYROscan']['assist']['getglobal.py'].filename, 'r') as _helper_source:
    exec(compile(_helper_source.read(), _helper_source.name, 'exec'), globals())

for paraxval_item in Range_x:
    for parayval_item in Range_y:
        for ky_item in kyarr:
            datanode=root['OUTPUTScan'][Para_x][num2str_xj(paraxval_item,effnum)][Para_y][num2str_xj(parayval_item,effnum)]['lin'][num2str_xj(ky_item,effnum)]
            dirname='parax_'+num2str_xj(paraxval_item,effnum)+'~paray_'+num2str_xj(parayval_item,effnum)+'~ky_'+num2str_xj(ky_item,effnum)
            mounttree[dirname]=copy.deepcopy(datanode)

# get the value
nfield=3
Qe_data=zeros([nfield,num_ky,nRange_x,nRange_y]) # 3 is for the number of fields
Qi_data=zeros([nfield,num_ky,nRange_x,nRange_y]) # the results of a given ion species
Ge_data=zeros([nfield,num_ky,nRange_x,nRange_y])
Gi_data=zeros([nfield,num_ky,nRange_x,nRange_y])
Pe_data=zeros([nfield,num_ky,nRange_x,nRange_y])
Pi_data=zeros([nfield,num_ky,nRange_x,nRange_y]) # for a given ion species
i_ion_species=1;
#
for p_ky, ky_value in enumerate(kyarr):
    for p_rangex in range(nRange_x):
        for p_rangey in range(nRange_y):
            dirname='parax_'+num2str_xj(Range_x[p_rangex],effnum)+'~paray_'+num2str_xj(Range_y[p_rangey],effnum)+'~ky_'+num2str_xj(ky_value,effnum)
            totals, raw, labels = ql_species_flux(mounttree[dirname], setup['icgyro'], i_ion_species, nfield)
            for key, values in [('Ge', Ge_data), ('Gi', Gi_data), ('Qe', Qe_data), ('Qi', Qi_data), ('Pe', Pe_data), ('Pi', Pi_data)]:
                values[:, p_ky, p_rangex, p_rangey] = totals[key]
# construct to xarray
Qe=xr.DataArray(data=Qe_data,
                coords={
                    "field":range(nfield),
                    "ky": kyarr,
                    "rangex": Range_x,
                    "rangey": Range_y,
                },
                dims=['field','ky','rangex','rangey'],
                )
Qi=xr.DataArray(data=Qi_data,
                coords={
                    "field":range(nfield),
                    "ky": kyarr,
                    "rangex": Range_x,
                    "rangey": Range_y,
                },
                dims=['field','ky','rangex','rangey'],
                )
Ge=xr.DataArray(data=Ge_data,
                coords={
                    "field":range(nfield),
                    "ky": kyarr,
                    "rangex": Range_x,
                    "rangey": Range_y,
                },
                dims=['field','ky','rangex','rangey'],
                )
Gi=xr.DataArray(data=Gi_data,
                coords={
                    "field":range(nfield),
                    "ky": kyarr,
                    "rangex": Range_x,
                    "rangey": Range_y,
                },
                dims=['field','ky','rangex','rangey'],
                )

Pe=xr.DataArray(data=Pe_data,
                coords={
                    "field":range(nfield),
                    "ky": kyarr,
                    "rangex": Range_x,
                    "rangey": Range_y,
                },
                dims=['field','ky','rangex','rangey'],
                )
Pi=xr.DataArray(data=Pi_data,
                coords={
                    "field":range(nfield),
                    "ky": kyarr,
                    "rangex": Range_x,
                    "rangey": Range_y,
                },
                dims=['field','ky','rangex','rangey'],
                )
Channel_arr=['Pe','Pi','Ge','Gi','Qe','Qi']
Para_x_dic={0:Para_x, 1: Para_y}
Para_y_dic={0:Para_y, 1: Para_x}
for p_field in range(nfield):
    for p_ky in range(num_ky):
        figure('field'+str(p_field)+'~ky'+str(kyarr[p_ky]),figsize=[16,10])
        for k in arange(1,7):
            axk=subplot(3,2,k)
            if idimplt==0:
                cmd='plot(Range_x,'+Channel_name[k-1]+'.isel(field=p_field,ky=p_ky,rangey=p_rangey),lab[p_rangey],label=str(Range_y[p_rangey]))'
                for p_rangey in range(nRange_y):
                    exec(cmd)
            else:
                cmd = 'plot(Range_y,' + Channel_name[k - 1] + '.isel(field=p_field,ky=p_ky,rangex=p_rangex),lab[p_rangex],label=str(Range_x[p_rangex]))'
                for p_rangex in range(nRange_x):
                    exec(cmd)
            axk.set_xscale(scale_dic[ilogx])
            axk.set_yscale(scale_dic[ilogy])
            legend(loc=0, fontsize=fs2).set_draggable(True)
            if k==5 or k==6:
                xlabel(Para_x_dic[idimplt], fontsize=fs1, family='serif')
            xticks(fontsize=fs2,family='serif')
            yticks(fontsize=fs2,family='serif')
            if k == 1 or k == 3 or k == 5:
                title(Channel_arr[k - 1], fontsize=fs1, family='serif')
            else:
                if i_ion_species == -1:
                    tag = '-sum'
                else:
                    tag = '-ion_' + str(i_ion_species)
                title(Channel_arr[k - 1] + tag, fontsize=fs1, family='serif')

# fieldsum
for p_ky in range(num_ky):
    figure('fieldsum~ky'+str(kyarr[p_ky]),figsize=[16,10])
    for k in arange(1,7):
        axk=subplot(3,2,k)
        if idimplt==0:
            cmd='plot(Range_x,sum('+Channel_name[k-1]+'.isel(ky=p_ky,rangey=p_rangey),axis=0),lab[p_rangey],label=str(Range_y[p_rangey]),linewidth=lw*2)'
            for p_rangey in range(nRange_y):
                exec(cmd)
        else:
            cmd = 'plot(Range_y,sum(' + Channel_name[k - 1] + '.isel(ky=p_ky,rangex=p_rangex),axis=0),lab[p_rangex],label=str(Range_x[p_rangex]),linewidth=lw*2)'
            for p_rangex in range(nRange_x):
                exec(cmd)
        axk.set_xscale(scale_dic[ilogx])
        axk.set_yscale(scale_dic[ilogy])
        legend(loc=0, fontsize=fs2).set_draggable(True)
        if k==5 or k==6:
            xlabel(Para_x_dic[idimplt], fontsize=fs1, family='serif')
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


# fieldsum to Qe ratio
for p_ky in range(num_ky):
    figure('fieldsum2Qe~ky'+str(kyarr[p_ky]),figsize=[16,10])
    for k in arange(1,7):
        axk=subplot(3,2,k)
        if idimplt==0:
            cmd='plot(Range_x,sum('+Channel_name[k-1]+'.isel(ky=p_ky,rangey=p_rangey),axis=0)/sum(Qe.isel(ky=p_ky,rangey=p_rangey),axis=0),lab[p_rangey],label=str(Range_y[p_rangey]),linewidth=lw*2)'
            for p_rangey in range(nRange_y):
                exec(cmd)
        else:
            cmd = 'plot(Range_y,sum(' + Channel_name[k - 1] + '.isel(ky=p_ky,rangex=p_rangex),axis=0)/sum(Qe.isel(ky=p_ky,rangex=p_rangex),axis=0),lab[p_rangex],label=str(Range_x[p_rangex]),linewidth=lw*2)'
            for p_rangex in range(nRange_x):
                exec(cmd)
        axk.set_xscale(scale_dic[ilogx])
        axk.set_yscale(scale_dic[ilogy])
        legend(loc=0, fontsize=fs2).set_draggable(True)
        if k==5 or k==6:
            xlabel(Para_x_dic[idimplt], fontsize=fs1, family='serif')
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


# write the flux out
iwriteflux=plots['iwriteflux']
if iwriteflux == 1:
    # Tidy output retains both scan coordinates, ky and field identity.
    dataset = xr.Dataset({'Ge': Ge, 'Gi': Gi, 'Qe': Qe, 'Qi': Qi, 'Pe': Pe, 'Pi': Pi})
    dataset.rename({'rangex': Para_x, 'rangey': Para_y}).to_dataframe().to_csv(root['SETTINGS']['DEPENDENCIES']['fluxout'])
    print('Wrote two-dimensional flux table')
