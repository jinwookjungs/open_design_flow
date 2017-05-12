#!/bin/bash

# Parameter check
contains() {
    for i in $1; do
        [[ $i = $2 ]] && return 1
    done
    return 0
}
if test "$#" -ne 6; then
    echo "Usage: ./run_sizer.sh <verilog> <sdc> <spef> <lib> <sizer> <out_dir>"
    echo "Available sizers: [USizer]"
    exit
elif contains "USizer" $5 = 0; then
    echo "Available sizers: [USizer]"
    exit
fi

verilog=$1
sdc=$2
spef=$3
lib=$4
sizer=$5
out_dir=$6

# output
log=${sizer}.log

# For run time measurement 
START=$(date +%s)

#------------------------------------------------------------------------------
# UFRGS Sizer
#------------------------------------------------------------------------------
if test "$sizer" = "USizer"; then
    # write config file
    config_file=usizer.config
    echo "$verilog $sdc $spef $lib" > $config_file

    cmd="../bin/usizer2013 -config ${config_file} open-eda"
    echo $cmd
    eval $cmd | tee ${log}
fi



END=$(date +%s)
RUN_TIME=$(( $END - $START ))
echo "" | tee --append $log
echo "Run time: $RUN_TIME" | tee --append $log
echo "" | tee --append $log
mv $log $out_dir
