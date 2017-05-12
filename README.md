# OpenDesign Flow Database
In recent years, there has been a slew of design automation contests and released benchmarks. 
Past examples include ISPD place & route contests, DAC placement contests, timing analysis contests at TAU, and CAD contests at ICCAD. 
Additional contests are planned for upcoming conferences. 
These are interesting and important events that stimulate the research of the target problems and advance the cutting edge technologies. 
Nevertheless, most contests focus only on the point tool problems and fail in addressing the design flow or co-optimization among design tools. 
OpenDesign Flow Database platform is developed to direct attention to the overall design flow from logic design to physical synthesis to manufacturability optimization. 
The goals are to provide 1) an academic reference design flow based on past CAD contest results, 2) the database for design benchmarks and point tool libraries, and 3) standard design input/output formats to build a customized design flow by composing point tool libraries.

## Getting Started
Basic flow consists of the following stages:

    Logic synthesis:      ./100_logic_synthesis
    Bookshelf generation: ./200_floorplanning
    Placement:            ./300_placement
    Timing measurement:   ./310_write_def
                          ./320_timing
    Gate sizing:          ./400_gate_sizing
                          ./410_write_bookshelf
                          ./420_legalization
                          ./430_write_def
                          ./440_timing
    Global routing:       ./500_gr_bench_gen
                          ./510_global_route

Every stage has the main run script (run_batch) in which you can specify 
the benchmark designs that you want to run as well as binaries.
After specifying designs and binaries in "run_batch" script, you can run 
each step simply by 

$ ./run_batch


## Benchmarks

You can specify the benchmark using the "bench_list" variable.
Currently, 4 designs from the ICCAD2014 TDP contest are available:
b19, vga_lcd, leon2, leon3mp, netcard, mgc_edit_dist, mgc_matrix_mult


## Logic Synthesis

ABC comes with various logic synthesis scripts, such as "resyn", "resyn2", 
etc. You can specify the synthesis script that ABC will use using 
"script_list" variable in "run_batch" script. The resulting verilog netlist 
will be named as 
```
<benchmark>_<script>_final.v
```

## Bookshelf Generation

Bookshelf files are generated given the synthesis result. You can run this 
stage with "run_batch" script after specifying the benchmarks and logic 
synthesis. The results will be stored at the directory named:
```
bookshelf_<benchmark>_<script>
```

## Placement

Currently, the following binaries are available (specified by placer_list):
Capo, NTUPlace3, ComPLx, mPL5, mPL6

After placement, you can see the placement plot. The plot file will be stored at:
```
<benchmark>_<ABC_script>_<Placer>"/"<benchmark>_<ABC_script>_<Placer>_plot.png
```


## Timing Measurement

To measure the timing with ICCAD evaluation program, we need to generate 
the def files of placement results. It will be done by "run_batch" script
inside the "310_write_def" directory.

After def file geneartion, you can measure the timing with the ICCAD evaluation
program at "320_timing" directory. All the files dumped by the ICCAD evaluation 
prgram will be stored at 

```
<benchmark>_<ABC_scipt>_<Placer>/out
```


## Global Routing

You can generate the global routing benchmarks after placement, using the 
"run_batch" at "500_gr_bench_gen" directory.

After the benchmark generation, you can now run global routing at 
"410_globla_route". Currently, "NCTUgr", "FastRoute", and "BFG-R" are available for 
global routing (you can specify the binary using "routing_list" variable).
After global routing, you can see the congestion map:

```
gr_<benchmark>_<ABC_script>_<Placer>_<Router>/<benchmark>.Max_H.congestion.png
gr_<benchmark>_<ABC_script>_<Placer>_<Router>/<benchmark>.Max_V.congestion.png
```

## Gate Sizing Flow
Gate sizing flow can be executed also by "run_batch" scripts, inside the following 
directories:
    
    ./400_gate_sizing
    ./410_write_bookshelf
    ./420_legalization
    ./430_write_def
    ./440_timing

## Reference
Jinwook Jung, Iris Hui-Ru Jiang, Gi-Joon Nam, Victor N. Kravets, Laleh Behjat, and Yin-Lang Li. 2016. OpenDesign flow database: the infrastructure for VLSI design and design automation research. In Proceedings of the 35th International Conference on Computer-Aided Design (ICCAD '16). ACM, New York, NY, USA, , Article 42 , 6 pages. DOI: https://doi.org/10.1145/2966986.2980074

## Authors
* [**Jinwook Jung**](mailto:jinwookjungs@gmail.com) - [KAIST](http://dtlab.kaist.ac.kr)
* **Gi-Joon Nam**

## Advisors
* Iris Hui-Ru Jiang
* Victor N. Kravets
* Laleh Behjat
* Yi-Lang Li
