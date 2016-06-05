cd stotramanjari
latexmk -xelatex stotramanjari-1 -g >> rebuild.log
latexmk -xelatex stotramanjari-2 -g >> rebuild.log
latexmk -xelatex stotramanjari-3 -g >> rebuild.log
latexmk -xelatex stotramanjari -g >> rebuild.log
latexmk -xelatex stotramanjari-rm -g >> rebuild.log
cd ..
cd nityaparayanam
latexmk -xelatex nityaparayanam -g >> rebuild.log
latexmk -xelatex nityaparayanam-vedam -g >> rebuild.log
latexmk -xelatex mantrapushpam-mini -g >> rebuild.log
cd ..
