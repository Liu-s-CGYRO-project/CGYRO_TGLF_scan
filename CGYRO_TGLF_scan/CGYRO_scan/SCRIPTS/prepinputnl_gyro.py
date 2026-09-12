print('please input the rho_star first')
inputgyro=root['INPUTS']['input.gyro']
# addjust line
#inputgyro['RADIAL_GRID']=128
#inputgyro['BOX_MULTIPLIER']=2
#inputgyro['RADIAL_GYRO_BAND']=16
#inputgyro['EXPLICIT_DAMP_GRID']=32
#inputgyro['TOROIDAL_GRID']=16
# inputline in case that the input.gyro is only a control profile
inputgyro['L_Y']=0.04
rho_star=0.005649 # rho_s/a
# calculate
q=inputgyro['SAFETY_FACTOR']
s=inputgyro['SHEAR']
ky=inputgyro['L_Y']
box_size=inputgyro['BOX_MULTIPLIER']
rmin=inputgyro['RADIUS']
# get the parameters for kx, donated by _x
n_x=inputgyro['RADIAL_GRID']
delta_x=2*pi*ky*s/box_size
max_x=(n_x/2.-1)*delta_x # gyro output is half of this value
Lx=box_size/ky/s
# get the parameters for ky, donated by _y
n_y=inputgyro['TOROIDAL_GRID']
delta_y=ky
max_y=(n_y-1)*ky
Ly=2*pi/ky
# print
print ('          n     Delta    Max    L/rho')
print ('kx : %7.0f %7.3f %7.3f %7.1f'%(n_x,delta_x,max_x,Lx))
print ('ky : %7.0f %7.3f %7.3f %7.1f'%(n_y,delta_y,max_y,Ly))
print('dx/rho_s=%7.2f'%(Lx/n_x))
# we will also have some suggestions for the maximum number of cores
n_lambda=inputgyro['PASS_GRID']+inputgyro['TRAP_GRID']
n_proc_max=inputgyro['ENERGY_GRID']*inputgyro['TOROIDAL_GRID']*n_lambda
print('The maximum core number that you can choose is:')
print(n_proc_max)
# get the gyro_band_width
m_gyro=inputgyro['RADIAL_GYRO_BAND']
#inputgyro=OMFIT['scratch']['input.gyro']
for k in arange(2,10):
    if not 'Z_'+str(k) in inputgyro.keys():
#        print(k)
        break
n_ion=k-1 # num of ion_species
rhoi_over_rhos=zeros(n_ion)
band=zeros(n_ion)
rhoi_over_rhos[0]=sqrt(inputgyro['TI_OVER_TE']/inputgyro['MU']/inputgyro['Z'])
num_rho=Lx/rhoi_over_rhos[0]
band[0]=(2*m_gyro+1)*num_rho/n_x
for k in arange(1,n_ion):
    rhoi_over_rhos[k]=sqrt(inputgyro['TI_OVER_TE_'+str(k+1)]/inputgyro['MU_'+str(k+1)]/inputgyro['Z_'+str(k+1)])
    num_rho=Lx/rhoi_over_rhos[k]
    band[k]=(2*m_gyro+1)*num_rho/n_x
print('RADIAL_GYRO_BANDs(rho_i,>10 is required)')
print(band)
# get the buffer_width (actually there exist buffer widths in the left and right boundary respectively)
# here we get the one in the r_norm, which should be in between the value in the left and right boundary respectively
n_explicit_damp=inputgyro['EXPLICIT_DAMP_GRID']
buffer=zeros(n_ion)
buffer[0]=n_explicit_damp*Lx/n_x/rhoi_over_rhos[0]
for k in arange(1,n_ion):
    buffer[k]=n_explicit_damp*Lx/n_x/rhoi_over_rhos[k]
print('BUFFER region(unit of rho_i,>8 is required)')
print(buffer)
# get the simulation range
rho_range=Lx*rho_star;
r_left=inputgyro['RADIUS']-rho_range/2;
r_right=inputgyro['RADIUS']+rho_range/2;
r_left_physical=r_left+n_explicit_damp*Lx/n_x*rho_star;
r_right_physical=r_right-n_explicit_damp*Lx/n_x*rho_star;
print('r_left %7.2f'%r_left)
print('r_left_physical %7.2f'%r_left_physical)
print('r_norm %7.2f'%inputgyro['RADIUS'])
print('r_right_physical %7.2f'%r_right_physical)
print('r_right %7.2f'%r_right)
# get the physical range equals to how many ion gyroradius
print('number of gyro radius in the physical simulation range for each ion species')
print((n_x-2*n_explicit_damp)*Lx/n_x/rhoi_over_rhos)
