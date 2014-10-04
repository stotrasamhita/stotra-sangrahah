#!/bin/bash
find ../stotras -name "*.tex" | while read fpath
do
fname=`basename $fpath`
SSURL=`echo $fname | sed 's/.tex//;s/[A-Z]/_&/g' | sed 's/^_//;s/(_/_(/'`
echo "---------------------------------------------------------------"
echo "File path         : $fpath"
jobname=`echo $fpath | sed 's/.tex//;s@.*stotras/@@'`
echo "PDF target        : $jobname.pdf"
echo "StotraSamhita URL : $SSURL"
mkdir -p `dirname $jobname`
if [[ $fpath -nt $jobname.pdf ]]
then
echo Rebuilding $jobname.pdf... > /dev/stderr
echo Rebuilding $jobname.pdf...
cat stotra-kindle-template.tex | sed "s@FPATH@$fpath@;s@SSURL@$SSURL@" | xelatex -jobname=$jobname
else
echo PDF up-to-date.
fi
done > tex2pdf.log
