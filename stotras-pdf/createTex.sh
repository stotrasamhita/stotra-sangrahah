#!/bin/bash
fpath=$1
fname=`basename $fpath`
SSURL=`echo $fname | sed 's/.tex//;s/[A-Z]/_&/g' | sed 's/^_//;s/(_/_(/'`
echo "---------------------------------------------------------------"
echo "File path         : $fpath"
jobname=`echo $fpath | sed 's/.tex//;s@.*stotras/@@'`
echo "PDF target        : $jobname.pdf"
echo "StotraSamhita URL : $SSURL"
# mkdir -p `dirname $jobname`
cat stotra-template.tex | sed "s@FPATH@$fpath@;s@SSURL@$SSURL@" | awk "{if(\$0~/input/){system(\"cat \" \"$1\")}
else{print}}" > $jobname.tex
echo TeX created: $jobname.tex

