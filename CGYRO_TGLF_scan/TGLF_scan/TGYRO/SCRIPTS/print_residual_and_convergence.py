# -*-Python-*-
# Created by smithsp at 2013/08/26 11:43

defaultVars(output=root['OUTPUTS']['output'], input_tgyro=root['INPUTS']['input.tgyro'])
if input_tgyro['TGYRO_RELAX_ITERATIONS'] < 1 and not input_tgyro['LOC_RESTART_FLAG']:
    printi('No TGYRO residual for # iterations = %d' % input_tgyro['TGYRO_RELAX_ITERATIONS'])
    OMFITx.End()
delta_sum = 0
for flag, q in [
    ('LOC_TI_FEEDBACK_FLAG', 'a/Lti1'),
    ('LOC_TE_FEEDBACK_FLAG', 'a/Lte'),
    ('TGYRO_DEN_METHOD0', 'a/Lne'),
    ('LOC_ER_FEEDBACK_FLAG', 'M=wR/cs'),
] + [('TGYRO_DEN_METHOD%d' % k, 'a/Lni%d' % k) for k in range(1, 10)]:
    if flag in input_tgyro and input_tgyro[flag] == 1:
        quant = output[q]
        delta_sum += abs((quant[1:, 1:-1] - quant[:-1, 1:-1]) / quant[1:, 1:-1]).sum(axis=1)
if sum(tolist(delta_sum)) == 0:
    delta_sum = [0]

# residual = output['residual']
convergence = output['convergence']
if len(convergence):
    print('Sum of residuals = %2.2f; Sum of driving profile changes = %2.2f' % (convergence[-1], delta_sum[-1]))
