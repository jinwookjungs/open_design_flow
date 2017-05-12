#!/bin/bash

if test "$#" -ne 5; then
    echo "Usage: ./run_fp.sh <bench> <netlist.v> <clock_port> <lef_file> <def_file>"
    exit
fi

bench=${1}
netlist=${2}
clock_port=${3}
lef=${4}
def=${5}

bench_dir="../bench"

logic_synth_dir="../10_logic_synth"

echo "Netlist: ${netlist}"
echo "--------------------------------------------------------------------------------"
cmd="python3 ../utils/200_gen_bookshelf.py -i ${netlist} --clock ${clock_port}"
cmd="$cmd --lef $lef --def $def --fix_big_blocks"
#cmd="$cmd --lef $lef" 
cmd="$cmd -o ${bench}"

echo $cmd; $cmd
echo ""


#echo "Restore terminal location"
#python3 merge_pl.py --nodes ${out_dir}/${base_name}.nodes --src ${out_dir}/${base_name}.pl	\
#                    --ref ${ref_bookshelf_path}/bookshelf-${bench}/${bench}.pl
#
#echo "Restore scl"
#cp ${ref_bookshelf_path}/bookshelf-${bench}/${bench}.scl ${out_dir}/${base_name}.scl
