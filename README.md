eth-stratum-mining-proxy
====================

This is fork of proxy created by Slush. 

Application providing bridge between Ethereum HTTP/getwork protocol and Stratum mining protocol
as described here: http://mining.bitcoin.cz/stratum-mining.

Installation on Windows
-----------------------

1. Download official Windows binaries (EXE) from https://github.com/feeleep75/eth-stratum-mining-proxy/releases/tag/v2.0
2. Open downloaded file. It will open console window. Using default settings, proxy connects to eth.coinmine.pl
3. Another way to start proxy: mining_proxy.exe -o eth.coinmine.pl -p 4000 
4. You can also download python sources from github and run: python mining_proxy.py -o eth.coinmine.pl -p 4000
4. If you want to connect to another pool or change other proxy settings ( for example define custom worker and password ), type "mining_proxy.exe --help" in console window.

Installation on Linux 
---------------------------------------

1. install twisted apt-get: 
	install python-twisted
2. download https://github.com/feeleep75/eth-stratum-mining-proxy/
3. run proxy: 
	python ./mining-proxy.py -o eth.coinmine.pl -p 4000
4. If you want to connect to another pool or change other proxy settings ( for example define custom worker and password ), type "mining_proxy.py --help".


Mining GPU
---------------------------------------

1. Start mining proxy
2. Start ethminer with following parameters:
	ethminer.exe --farm-recheck 200 -G -F http://127.0.0.1:8332/workername:workerpassword

Contact
-------

You can contact the author by email support(at)coinmine.pl


