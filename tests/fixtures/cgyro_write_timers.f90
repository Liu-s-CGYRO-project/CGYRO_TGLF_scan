subroutine write_timers(datafile)

  use mpi
  use cgyro_globals
  use timer_lib

  !-----------------------------------------------
  implicit none
  !
  character (len=*), intent(in) :: datafile
  integer :: i_dummy
  real, dimension(11) :: dummy
  character (len=2) :: sdummy
  !-------------------------------------------------

  if (io_control == 1 .or. io_control == 3) then
     ! Timer initialization (starts at timer 6)
     call timer_lib_init('str')
     call timer_lib_init('str_mem')
     call timer_lib_init('str_comm')
     call timer_lib_init('nl')
     call timer_lib_init('nl_mem')
     call timer_lib_init('nl_comm')
     call timer_lib_init('field')
     call timer_lib_init('field_com')
     call timer_lib_init('shear')
     call timer_lib_init('coll')
     call timer_lib_init('coll_mem')
     call timer_lib_init('coll_comm')
     call timer_lib_init('io')
     call timer_lib_init('TOTAL')
     call timer_lib_init('nlc_fft_fA_launch')
     call timer_lib_init('nlc_fft_fB_launch')
     call timer_lib_init('nlc_fft_g_launch')
     call timer_lib_init('nlc_fft_fA_wait')
     call timer_lib_init('nlc_fft_g_wait')
     call timer_lib_init('nlc_fft_revA')
     call timer_lib_init('nlc_fft_fB_wait')
     call timer_lib_init('nlc_fft_revB')
     call timer_lib_init('nlc_rhs_fA_wait')
     call timer_lib_init('nlc_rhs_fB_wait')
     call timer_lib_init('nlc_rhs_eA_wait')
     call timer_lib_init('nlc_rhs_eB_wait')
  endif

  select case (io_control)

  case(0)

     return

  case (1)

     ! Initial open
     if (i_proc == 0) then
        open(unit=io,file=datafile,status='replace')
        write(io,'(a)') 'Setup time'
        ! align for f10.3, i.e. at least 6 chars, last empty
        write(io,'(1x,9(a10,2x))') &
             '    input ', &
             ' str_init ', &
             '  nl_init ', &
             'coll_init ', &
             '  io_init '
        write(io,'(9(f10.3,2x))') &
             timer_lib_time('input'),&
             timer_lib_time('str_init'),&
             timer_lib_time('nl_init'),&
             timer_lib_time('coll_init'),&
             timer_lib_time('io_init')
        write(io,'(a)') 'Run time'
        ! align for f10.3, i.e. at least 6 chars, last empty
        write(io,'(1x,14(a10,1x))') &
             '    str   ', &
             '  str_mem ', &
             ' str_comm ', &
             '    nl    ', &
             '   nl_mem ', &
             '  nl_comm ', &
             '    field ', &
             'field_com ', &
             '    shear ', &
             '    coll  ', &
             ' coll_mem ', &
             'coll_comm ', &
             '    io    ', &
             '    TOTAL '
        close(io)
     endif
     call write_timers_debug(trim(path)//runfile_timers_debug,io_control)

  case (2)

     !---------------------------------------------------------------------------
     ! Print timers

     call MPI_barrier(CGYRO_COMM_WORLD,i_err)

     if (i_proc == 0) then
        open(unit=io,file=datafile,status='old',position='append')
        write(io,'(14(f10.3,1x))') &
             timer_lib_time('str'),& 
             timer_lib_time('str_mem'),&
             timer_lib_time('str_comm'),& 
             timer_lib_time('nl'),& 
             timer_lib_time('nl_mem'),&
             timer_lib_time('nl_comm'),&
             timer_lib_time('field'),&
             timer_lib_time('field_com'),&
             timer_lib_time('shear'),&
             timer_lib_time('coll'),&
             timer_lib_time('coll_mem'),&
             timer_lib_time('coll_comm'),&
             timer_lib_time('io'),& 
             timer_lib_time('TOTAL') 
        close(io)
     endif
     call write_timers_debug(trim(path)//runfile_timers_debug,io_control)
     !---------------------------------------------------------------------------

     ! Reset all timers
     timer_cpu = 0.0

  case (3)

     ! Rewind

     if (i_proc == 0) then 
        open(unit=io,file=datafile,status='old')
        read(io,'(a)') sdummy
        read(io,'(a)') sdummy
        read(io,'(a)') sdummy
        read(io,'(a)') sdummy
        read(io,'(a)') sdummy
        do i_dummy=1,i_current
           read(io,*) dummy(1)
        enddo
        endfile(io,iostat=i_dummy)
        close(io)
     endif

     ! Reset all timers
     timer_cpu = 0.0

  end select

end subroutine write_timers
