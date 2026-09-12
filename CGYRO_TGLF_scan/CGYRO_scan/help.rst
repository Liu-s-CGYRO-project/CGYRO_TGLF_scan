CGYRO scan project
==================

This project contains CGYRO scan preparation, result collection and plotting.
The saved example is a two-species electromagnetic linear scan. Solver and
cluster environments must be configured on the machine that will run it.

Workflow
--------

1. Review INPUTS/input.cgyro and SETTINGS/PHYSICS. The 1d or 2d subtree defines
   scan parameters; kyarr supplies the positive wave numbers.
2. Select SETTINGS/REMOTE_SETUP/serverPicker and review that server's executable,
   environment, scheduler and workDir. serverPicker=localhost requires the local
   scheduler. No executable or cluster login is supplied automatically.
3. Use Prepare inputs only to validate and package the inputs without submitting.
   Review RUN_MANIFEST and its per-input SHA256 values.
4. Run configured scan uses SETUP/irun and idownsync. Each preparation creates a
   unique runs/<token> directory. The old Cases and OUTPUTScan are preserved in
   RUN_HISTORY; archived RUN_DB data are not silently relabelled.
5. Plot settings must select points present in OUTPUTScan. Plotting uses a
   separate _PLOT_CACHE and never removes saved OUTPUTS.

Restart and limitations
-----------------------

restart_mode=1 requires a saved matching point and bin.cgyro.restart. Only
MAX_TIME and PRINT_STEP may change; other input changes require a fresh run.
A restart is copied into a new directory so the original result stays intact.
Failed parsing is reported and the prior result is preserved.

Quasilinear/nonlinear comparisons require an explicit
PLOTS/nl/linear_range_by_case mapping and compatible species/field input metadata.
There is no automatic mapping between H, D and T runs. The old private-directory
updater and unverified GYRO submission backend are disabled. Distribution and
preserve-current/load-example update selection are separate future work.

The repair was validated with isolated regression fixtures; it has not run a
real solver, cluster submission or a full OMFIT GUI session.
