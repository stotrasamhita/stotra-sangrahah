#!/bin/bash
#
# Usage: find ../stotras -name "*.tex" | while read x; do ./tex2pdf.sh $x; done
#
fpath=$1
fname=`basename $1`
SSURL=`echo $fname | sed 's/.tex//;s/[A-Z]/_&/g' | sed 's/^_//;s/(_/_(/'`
echo "StotraSamhita URL: $SSURL"
echo "File path: $fpath"
jobname=`echo $fpath | sed 's/.tex//;s@.*stotras/@@'`
echo "Job Name: $jobname"
mkdir -p `dirname $jobname`
cat stotra-template.tex | sed "s@FPATH@$fpath@;s@SSURL@$SSURL@" | xelatex -jobname=$jobname
