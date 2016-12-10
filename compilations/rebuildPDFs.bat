cd stotramanjari
latexmk -xelatex stotramanjari-1 >> rebuild.log
latexmk -xelatex stotramanjari-2 >> rebuild.log
latexmk -xelatex stotramanjari-3 >> rebuild.log
latexmk -xelatex stotramanjari >> rebuild.log
latexmk -xelatex stotramanjari-rm >> rebuild.log
cd ..
cd nityaparayanam
latexmk -xelatex nityaparayanam-shloka >> rebuild.log
latexmk -xelatex nityaparayanam-vedam >> rebuild.log
latexmk -xelatex mantrapushpam-mini >> rebuild.log
cd ..
