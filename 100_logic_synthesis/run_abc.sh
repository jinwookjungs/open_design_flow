#!/bin/bash

if test "$#" -ne 3; then
    echo "Usage: ./run_abc.sh <circuit name> <synth script>"
    exit
fi

bench=${1}
synth_script=${2}
max_fo=${3}

bench_dir="../bench"
abc_bin="../bin/abc"
abc_rc="../bin/abc.rc"

bench_verilog=${bench_dir}/${bench}/${bench}.v
bench_genlib=${bench_dir}/${bench}/${bench}.genlib
bench_lib=${bench_dir}/${bench}/${bench}_Late.lib

input_blif=${bench}_${synth_script}.blif
output_verilog=${bench}_${synth_script}.v

final_verilog=${bench}_${synth_script}_final.v
latch="ms00f80"
clk_src="iccad_clk"

#-----------------------------------------------------------------------------
echo "LOGIC SYNTHESIS WITH ABC"
echo ""
echo "1. Verilog to blif conversion"
echo "------------------------------------------------------------------------------"
cmd="python3 ../utils/100_verilog_to_blif.py -i $bench_verilog -o $input_blif"
echo $cmd; $cmd

echo ""
echo "2. ABC synthesis - $bench"
echo "------------------------------------------------------------------------------"
$abc_bin -o $input_blif -c "
source $abc_rc;
read $bench_lib;
read $input_blif;
print_stats;
print_gates;
print_fanio;
unmap;
$synth_script;
map;
cleanup;
buffer -N $max_fo -v;
print_stats;
print_gates;
print_fanio;
write_verilog $output_verilog
"

echo ""
echo "3. Latch mapping - $bench"
echo "------------------------------------------------------------------------------"
cmd="python3 ../utils/100_map_latches.py -i $output_verilog --latch $latch --clock $clk_src"
cmd="$cmd -o $final_verilog"
echo $cmd; $cmd

echo "mkdir ${bench}_${synth_script}"
mkdir ${bench}_${synth_script}
echo "find . -maxdepth 1 -type f -name \"${bench}_${synth_script}*\" -exec mv {} ${bench}_${synth_script} \;"
find . -maxdepth 1 -type f -name "${bench}_${synth_script}*" -exec mv {} ${bench}_${synth_script} \;

echo "------------------------------------------------------------------------------"
echo ""
echo ""
