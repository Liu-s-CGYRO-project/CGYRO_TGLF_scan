# The linear run script of CGYRO
root = OMFIT['CGYRO_TGLF_scan']['CGYRO_scan']
import numpy as np
sys.path.append('/public/home/jinyue_liu/bin/GACODE_module/mymodule/PLOTS/CGYROscan/assist')
sys.path.append('/public/home/jinyue_liu/bin/GACODE_module/mymodule/PLOTS/CGYROalone/assist')
module_location = OMFIT['CGYRO_TGLF_scan']['CGYRO_scan']
for k in array(['H','D','T']):

    module_location['Cases'].clear()
    module_location['OUTPUTScan'].clear()
    module_location['SETTINGS']['PHYSICS']['nr']=2
    inputs = module_location['INPUTS']
    settings = module_location['SETTINGS']
    setup = settings['SETUP']
    rmtsetup = settings['REMOTE_SETUP']
    physics = settings['PHYSICS']
    phy1d=physics['1d']
#   phy1d=physics['2d']
    physics['mass']=k

    # Copy file from server to OMFIT

    use_the_local_input = False
    use_the_file_in_Transfer_Tool = True
    #You can copy the input file from the dirpath auto or copy it manually or from the Transfer_tool

    if not use_the_local_input:

        if use_the_file_in_Transfer_Tool:

            inputs['input.cgyro']=OMFITgacode(OMFIT['CGYRO_TGLF_scan']['Transfer_tool']['OUTPUTS']['Profiles_gen_'+k+'_simplified']['input.cgyro_'+str(1)]).duplicate()
        else:

            dirpath = '/data/share/jinyue_liu/UKAEA/Data/TGYRO/from our OMFIT/modify_qpar_beam_w0_qline/Profiles_gen_wo_fast_ions_mult_scale/'
            inputs['input.cgyro']=OMFITgacode(dirpath+'input.cgyro_'+str(1))

    inputcgyro=inputs['input.cgyro']
    inputs['input.cgyro_bak']=inputcgyro.duplicate()
    inputcgyro_bak=inputs['input.cgyro_bak']


    # Node and directory setup
    setup['num_nodes']=1
    setup['num_cores']=16
    setup['wall_time']='24:00:00'
    setup['pbs_queue']='parallel31'
    setup['effnum']=5
    setup['idimrun']=1
    rmtsetup['serverPicker']='login114'#'login112'
    rmtsetup['workDir']='06'


    # Prepare for linear calculation
    inputcgyro['NONLINEAR_FLAG']=0     #Nonlinear terms OFF
    inputcgyro['GAMMA_E_SCALE']=0      #Close the ExB for linear scan
    inputcgyro['N_TOROIDAL']=1         #Number of toroidal harmonics
    inputcgyro['PROFILE_MODEL']=1      #Set local profile parameters in input.cgyro
    inputcgyro['EQUILIBRIUM_MODEL']=2  #Miller parameterization


    # Resolution
    inputcgyro['DELTA_T']=0.01         #Simulation timestep
    inputcgyro['PRINT_STEP']=100       #Frequency of simulation data output
    inputcgyro['DELTA_T_METHOD']=1     #Control for adaptive or fixed time-stepping
    inputcgyro['ERROR_TOL']=1.e-5      #Error tolerance
    inputcgyro['MAX_TIME']=400         #Simulation time
    inputcgyro['N_RADIAL']=16          #Number of radial grid points
    inputcgyro['N_THETA']=48           #Number of poloidal grid points
    inputcgyro['THETA_PLOT']=1         #Number of plotted points in theta
    inputcgyro['FREQ_TOL']=1.e-3       #Error tolerance for frequency
    # del inputcgyro['SBETA']

    # Some other important setting
    inputcgyro['N_FIELD']=1            #1:Phi  2:Phi+Bprep  3:Phi+Bprep+Bparp
    inputcgyro['BOX_SIZE']=1           #Radial domain size
    inputcgyro['N_XI']=16              #Number of pitch angle grid points
    inputcgyro['N_ENERGY']=8           #Number of energy grid points
    inputcgyro['BETA_STAR_SCALE'] = 1
    inputcgyro['COLLISION_MODEL'] = 1
    inputcgyro['GAMMA_E'] = 0
    inputcgyro['GAMMA_P'] = 0
    inputcgyro['MACH'] = 0
    # Start to scan
    # scale_fac=np.linspace(6,8,2)
    # scale_fac=np.linspace(0.5,2.5,21)
    # scale_fac=np.logspace(-1,1,5)
    scale_fac=np.array([0])
    # phy1d['Para']='BETAE_UNIT'
    # phy1d['Range']=array(inputcgyro[phy1d['Para']]*scale_fac)#e

    phy1d['Para']='BETAE_UNIT'
    phy1d['Range']=array(inputcgyro[phy1d['Para']]*scale_fac)#e


    # phy1d['Para']='N_ENERGY'
    # phy1d['Range']=array(inputcgyro[phy1d['Para']]*scale_fac)#e
    # phy1d['Range']=array([int(num) for num in inputcgyro[phy1d['Para']]*scale_fac])

    # scale_fac=np.linspace(0.5,1.5,10)
    # phy1d['Para']='DLNNDR_5'
    # phy1d['Range']=array(inputcgyro[phy1d['Para']]*scale_fac)#e

    # phy1d['Para2']='DLNNDR_1'
    # ni1 = inputcgyro['DENS_1']
    #ni2 = inputcgyro['DENS_2']
    #ni3 = inputcgyro['DENS_3']
    #ni4 = inputcgyro['DENS_4']
    #ni5 = inputcgyro['DENS_5']
    #dlnndr2 = inputcgyro['DLNNDR_2']
    #dlnndr3 = inputcgyro['DLNNDR_3']
    #dlnndr4 = inputcgyro['DLNNDR_4']
    #dlnndre = inputcgyro['DLNNDR_6']
    #phy1d['Range2']=array((dlnndre-dlnndr2*ni2*4-dlnndr3*ni3*28-dlnndr4*ni4-phy1d['Range']*ni5*2)/ni1)#e

    #scale_fac3=np.array([10]*11)
    #phy1d['Para3']='TEMP_5'
    #phy1d['Range3']=array(inputcgyro[phy1d['Para']]*scale_fac3)#e



    # del phy1d['Para2']
    # del phy1d['Range2']



    # phy1d['Para2']='BETA_STAR_SCALE'
    # phy1d['Range2']=array(inputcgyro[phy1d['Para2']]/scale_fac)#e


    # Set the ky array for linear scan
    # physics['kyarr'] = array(np.linspace(0.03,0.9,30))
    # physics['kyarr'] = array(np.linspace(0.05,1.0,20))
    # physics['kyarr'] = array(np.linspace(0.02,0.6,30))
    physics['kyarr'] = array(np.linspace(0.1,1.6,16))
    # physics['kyarr'] = array(np.logspace(-1.2,1.5,40))
    # rho_array = linspace(0.2,0.85,8)
    # ky = OMFIT['CGYRO_TGLF_scan']['TGLF_scan']['scanResults_spectra'][round(rho_array[k-1],2)]['SAT_RULE'][3.0]['eigenvalue_spectrum']['ky']
    # physics['kyarr'] = array(ky)
    physics['mode']='lin'


    # Change the plot parameter
    settings['PLOTS']['1d']['Para'] = phy1d['Para']
    settings['PLOTS']['1d']['Range'] = phy1d['Range']
    settings['PLOTS']['kyarr'] = physics['kyarr']

    settings['PLOTS']['ky_eigen'] = physics['kyarr']
    settings['PLOTS']['1d']['para_eigen'] = phy1d['Range']




    # Run ID
    EXPERIMENT=settings['EXPERIMENT']
    EXPERIMENT['runid'] = 'Jet'

    module_location['SCRIPTS']['runCGYRO.py'].run()
