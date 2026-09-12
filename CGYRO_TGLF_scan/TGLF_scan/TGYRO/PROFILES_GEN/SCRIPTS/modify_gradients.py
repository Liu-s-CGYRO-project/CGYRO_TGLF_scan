# Modify input.gacode variables and save as input.gacode.[ext]


"""
Original script written by grierson to modify gradients of input profiles at the core.
Script scales profiles gradients at the core and save results in the new input.gacode file.
TGYRO solution is unique with the same boundary and initial conditions, but starting with lower gradients can help to get faster convergance.



defaultVars parameters
----------------------
prg - location of PROFILE_GEN module
inp - input.gacode file we want to modify
quant - plasma quantities for which profiles should be scaled
bc - boundary condition point
scale - scale parameter
write - True if file should be saved in PROFILE_GEN module
ext - extention for a new input.gacode file name

"""

defaultVars(
    prg=root,
    inp=root['OUTPUTS']['input.gacode.mod'],
    quants=scratch['quants_modGrad'],
    bc=scratch['bc_modGrad'],
    scale=scratch['scale_modGrad'],
    write=scratch['write_modGrad'],
    ext=scratch['ext_modGrad'],
)


def grad_mod(inp, quant, bc, scale):
    # rmin [m]
    rmin = inp['rmin']
    rho = inp['rho']
    var = inp[quant]
    grad = deriv(rmin, var)

    idx = where(rho <= bc)[0]
    grad[idx] *= scale

    # Reconstruct shape.
    var_scale = cumtrapz(grad[idx], rmin[idx], initial=0)
    # Remove constant of integration
    var_scale -= var_scale[-1]
    # Add in proper boundary condition
    var_scale += var[idx[-1]]
    # Append with profile outside boundary condition
    var_scale = np.append(var_scale, var[idx[-1] + 1 :])

    return var_scale


# copy original input.gacode file
inp_new = copy.deepcopy(inp)

for quant in quants:
    var_scale = grad_mod(inp, quant, bc, scale)
    inp_new[quant] = var_scale


if scratch['plot_modGrad']:
    if not quants:
        raise OMFITexception('Select at least one profile to plot')
    fig, ax = plt.subplots(ncols=len(quants), squeeze=False)
    ax = ax.ravel()
    for i, quant in enumerate(quants):
        ax[i].plot(inp['rho'], inp[quant], label='input.gacode')
        ax[i].plot(inp_new['rho'], inp_new[quant], label=f"input.gacode.{ext}")
        ax[i].set_title(quant)
        ax[i].legend()
        ax[i].set_xlabel(r'$\rho$')

if write:
    root['OUTPUTS']['input.gacode.{}'.format(ext)] = inp_new
