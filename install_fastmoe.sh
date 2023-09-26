#!/bin/bash

srun -N 1 -p V100 --ntasks-per-node=1 -- python  /home/qi/fastmoe_llm/setup.py install --user
