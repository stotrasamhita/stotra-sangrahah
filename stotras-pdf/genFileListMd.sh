#!/bin/bash
find | grep pdf$ | awk -F '/' '{
if ($2!=old2)
	{
		deityName=toupper(substr($2,1,1)) tolower(substr($2,2))
		print ("\n\n###",deityName, "Stotras"); old2=$2;
	}
	stotraName=$3
	sub(/.pdf/,"",stotraName)
	gsub(/[A-Z()]/," &",stotraName)
	print ("*" stotraName, "[A5](https://github.com/stotrasamhita/stotra-sangrahah/raw/master/stotras-pdf/" $2 "/" $3 ")", "[Kindle PDF](https://github.com/stotrasamhita/stotra-sangrahah/raw/master/stotras-kindle-pdf/" $2 "/" $3 ")")
}'

