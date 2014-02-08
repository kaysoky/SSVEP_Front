#!/bin/bash
FILES=(*.mat)

set -m

for file in "${FILES[@]}"; do
    #echo "python naive.py $file"
    python naive.py $file &
done

while [ 1 ]; do fg 2> /dev/null; [ $? == 1 ] && break; done
