# this script is used to plot the eigenfrequency and growth rate for all the scanning cases,
import sys
from OMFITlib_cgyro_read import *
from matplotlib import ticker
with open(root['PLOTS']['CGYROscan']['assist']['getglobal.py'].filename, 'r') as _helper_source:
    exec(compile(_helper_source.read(), _helper_source.name, 'exec'), globals())

# then read all the data
w_arr=zeros([nRange_x,nRange_y,num_ky])     # dominate mode frequency
err_w_arr=zeros([nRange_x,nRange_y,num_ky])     # error in dominate mode frequency
gamma_arr=zeros([nRange_x,nRange_y,num_ky]) # dominate mode growth rate
err_gamma_arr=zeros([nRange_x,nRange_y,num_ky]) # error in dominate mode growth rate
for k in range(nRange_x):
    for p in range(nRange_y):
        for q in range(num_ky):
            try:
                datanode=root['OUTPUTScan'][Para_x][num2str_xj(Range_x[k],effnum)][Para_y][num2str_xj(Range_y[p],effnum)]['lin'][num2str_xj(kyarr[q],effnum)]
                flag_read=1
                w,err_w=readfreq(datanode,flag_read)
                if ibelow0[0]==1:
                    if w[1]<ibelow0[1]:
                        w[1]=ibelow0[1]
            except:
 #            print('not work.')
                 w=array([0,0])
                 err_w=array([1,1])
            w_arr[k][p][q]=w[0]
            gamma_arr[k][p][q]=w[1]
            err_w_arr[k][p][q]=err_w[0]
            err_gamma_arr[k][p][q]=err_w[1]
### see whether we can get the s-alpha value from the WholeInfo module
# the Experimental value in the dependency=root['SETTINGS']['DEPENDENCIES'] should be filled before setting IpltExpalphas=1
# generally I like to use the dependency tree to interact with external data
IpltExpalphas=plt2d['ipltexp']
Ind_start=2
Ind_end=12
dependency=root['SETTINGS']['DEPENDENCIES']
if 'Val_x' in dependency.keys() and 'Val_y' in dependency.keys():
    Val_x_exp=dependency['Val_x']
    Val_y_exp = dependency['Val_y']
    rmin_exp = dependency['rmin']
if IpltExpalphas==1:
    plt2d['Val_x']=Val_x_exp[Ind_start:Ind_end]
    plt2d['Val_y'] = Val_y_exp[Ind_start:Ind_end]
########################################
# allows for scale of range_x and range_y
x_scale=plt2d['x_scale']
y_scale=plt2d['y_scale']
Para_x_display=plt2d['Para_x_display']
Para_y_display=plt2d['Para_y_display']
# based on the profiles we get, then all the linear information can be plotted
Para_x_dic={0:Para_x_display, 1: Para_y_display}
Para_y_dic={0:Para_y_display, 1: Para_x_display}
bdry_dic=[0.3, 1.e-4, 0.10, 1.e-4]
freqarr=['w_arr','err_w_arr','gamma_arr','err_gamma_arr']
if idimplt==0:
    Range_x_grid,Range_y_grid=meshgrid(x_scale*Range_x,y_scale*Range_y)
else:
    Range_x_grid,Range_y_grid=meshgrid(y_scale*Range_y,x_scale*Range_x)
for k in range(num_ky):
    fig=figure(kyarr[k],figsize=[10,10])
    ax = fig.gca()
    for p in arange(1,5):
        axp=subplot(2,2,p)
        if p==1 or p==3:
            if idimplt==0:
                cmd="contourf(x_scale*Range_x,y_scale*Range_y,"+freqarr[p-1]+".T[k],cmap='seismic',levels=36)"
                xlim(x_scale*array([min(Range_x),max(Range_x)]))
                ylim(y_scale * array([min(Range_y), max(Range_y)]))
            else:
                cmd="contourf(y_scale*Range_y,x_scale*Range_x,"+freqarr[p-1]+".T[k].T,cmap='seismic',levels=36)"
                xlim(y_scale*array([min(Range_y),max(Range_y)]))
                ylim(x_scale *array( [min(Range_x), max(Range_x)]))
                # we can also add the functunality of plot expeirental plot and mapped it here
            if IpltExpalphas == 1:
                print('rmin_exp Range=', [rmin_exp[Ind_start], rmin_exp[Ind_end]])
                if idimplt == 0:
                    plot(plt2d['Val_x'], plt2d['Val_y'], '-wo', linewidth=lw, markersize=ms)
                else:
                    plot(plt2d['Val_y'], plt2d['Val_x'], '-wo', linewidth=lw, markersize=ms)
        else:
            if idimplt==0:
                cmd="contourf(x_scale*Range_x,y_scale*Range_y,"+freqarr[p-1]+".T[k],locator=ticker.LogLocator(),cmap='seismic')"
            else:
                cmd="contourf(y_scale*Range_y,x_scale*Range_x,"+freqarr[p-1]+".T[k].T,locator=ticker.LogLocator(),cmap='seismic')"
        exec(cmd)
        axp.set_xscale(scale_dic[ilogx])
        axp.set_yscale(scale_dic[ilogy])
        if p == 3 or p == 4:
            xlabel(Para_x_dic[idimplt], fontsize=fs1, family='serif')
        if p == 1 or p == 3:
            ylabel(Para_y_dic[idimplt], fontsize=fs1, family='serif')
        #        if p==2 or p==4:
        #	    axp.set_zscale('log')
        xticks(fontsize=fs2, family='serif')
        yticks(fontsize=fs2, family='serif')
        title(freqarr[p - 1], fontsize=fs1, family='serif')
        colorbar()
        if idimplt==0:
            cmd="cs=contour(Range_x_grid,Range_y_grid,"+freqarr[p-1]+".T[k],["+str(bdry_dic[p-1])+"])"
        else:
            cmd="cs=contour(Range_y_grid,Range_x_grid,"+freqarr[p-1]+".T[k].T, ["+str(bdry_dic[p-1])+"])"
        exec(cmd)
        try:
            pp = cs.collections[0].get_paths()[1]
            v = pp.vertices
            plot(v[:,0],v[:,1],'--r',linewidth=lw*2)
            if p==3:                # 1: use omega; 3: use gamma; as the criterial to plot the boundary
                print(v[:,0])
                print(v[:, 1])
        except:
            print('not work at subplot '+str(p))
            continue

# # ===================================
iwritelin=plots['iwritelin']  # determine whether to write out to a file
nmodes=1
if iwritelin==1 and 'linout' in root['SETTINGS']['DEPENDENCIES'].keys():
    eigenout=root['SETTINGS']['DEPENDENCIES']['linout']
    fid=open(eigenout,'w')
# first write the scanned parameter name into the file
    fid.write(Para_x+'    '+Para_y)
    fid.write('\n')
# write the nRange and the para_val into the file
    fid.write(str(len(Range_x))+'    '+str(len(Range_y)))
    fid.write('\n')
    line=''
    for m in range(len(Range_x)):
        line=line+str(Range_x[m])+'    '
    fid.write(line)
    fid.write('\n')
    line=''
    for m in range(len(Range_y)):
        line=line+str(Range_y[m])+'    '
    fid.write(line)
    fid.write('\n')
# write nmodes into the file
    fid.write(str(nmodes)+'    '+str(num_ky))
    fid.write('\n')
    for k in range(num_ky):
        line=str(kyarr[k])
        for p in range(len(Range_x)):
            for q in range(len(Range_y)):
# w_arr=zeros([nRange_x,nRange_y,num_ky])
#            line=line+'    '+str(w_arr[p][k])+'    '+str(gamma_arr[p][k])+'    '+str(err_w_arr[p][k])+'    '+str(err_gamma_arr[p][k])
                line=line+'    '+str(w_arr[p][q][k])+'    '+str(gamma_arr[p][q][k])
        fid.write(line)
        fid.write('\n')
    fid.close()
