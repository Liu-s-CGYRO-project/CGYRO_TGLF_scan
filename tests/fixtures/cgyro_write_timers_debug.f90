subroutine write_timers_debug(datafile,mode)

  use mpi
  use cgyro_globals
  use timer_lib

  implicit none

  character(len=*), intent(in) :: datafile
  integer, intent(in) :: mode

  integer, parameter :: n_std = 14
  integer, parameter :: n_nlc = 12
  integer, parameter :: n_all = n_std+n_nlc
  character(len=19), dimension(n_all) :: tags
  double precision, dimension(n_all) :: local_time
  double precision, dimension(n_all) :: min_time
  double precision, dimension(n_all) :: max_rank_time
  double precision, dimension(n_all) :: sum_time
  integer :: itimer

  tags = (/ &
       'str                ', &
       'str_mem            ', &
       'str_comm           ', &
       'nl                 ', &
       'nl_mem             ', &
       'nl_comm            ', &
       'field              ', &
       'field_com          ', &
       'shear              ', &
       'coll               ', &
       'coll_mem           ', &
       'coll_comm          ', &
       'io                 ', &
       'TOTAL              ', &
       'nlc_fft_fA_launch  ', &
       'nlc_fft_fB_launch  ', &
       'nlc_fft_g_launch   ', &
       'nlc_fft_fA_wait    ', &
       'nlc_fft_g_wait     ', &
       'nlc_fft_revA       ', &
       'nlc_fft_fB_wait    ', &
       'nlc_fft_revB       ', &
       'nlc_rhs_fA_wait    ', &
       'nlc_rhs_fB_wait    ', &
       'nlc_rhs_eA_wait    ', &
       'nlc_rhs_eB_wait    ' /)

  select case (mode)

  case (1)
     if (i_proc == 0) then
        open(unit=io,file=datafile,status='replace')
        write(io,'(a)') '# CGYRO timing debug'
        write(io,'(a)') '# Values are accumulated over the same print window as out.cgyro.timing.'
        write(io,'(a)') '# Columns: timer rank0 min avg max'
        close(io)
     endif

  case (2)
     do itimer=1,n_all
        local_time(itimer) = dble(timer_lib_time(trim(tags(itimer))))
     enddo

     call MPI_ALLREDUCE(local_time,min_time,n_all,MPI_DOUBLE_PRECISION,MPI_MIN, &
          CGYRO_COMM_WORLD,i_err)
     call MPI_ALLREDUCE(local_time,max_rank_time,n_all,MPI_DOUBLE_PRECISION,MPI_MAX, &
          CGYRO_COMM_WORLD,i_err)
     call MPI_ALLREDUCE(local_time,sum_time,n_all,MPI_DOUBLE_PRECISION,MPI_SUM, &
          CGYRO_COMM_WORLD,i_err)

     if (i_proc == 0) then
        open(unit=io,file=datafile,status='old',position='append')
        write(io,'(a,i10,1x,a,1pe14.6)') '# i_time ',i_time,'t_current ',t_current
        do itimer=1,n_std
           write(io,'(1x,a19,4(1x,1pe14.6))') trim(tags(itimer)), &
                local_time(itimer),min_time(itimer),sum_time(itimer)/dble(n_proc), &
                max_rank_time(itimer)
        enddo
        write(io,'(a)') '# nl_comm detail'
        do itimer=n_std+1,n_all
           write(io,'(1x,a19,4(1x,1pe14.6))') trim(tags(itimer)), &
                local_time(itimer),min_time(itimer),sum_time(itimer)/dble(n_proc), &
                max_rank_time(itimer)
        enddo
        close(io)
     endif

  end select

end subroutine write_timers_debug
